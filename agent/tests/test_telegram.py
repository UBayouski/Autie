"""Tests for the Telegram channel adapter (app/channels/telegram.py)."""

import os

os.environ["AUTH_DISABLED"] = "true"
os.environ["SESSIONS_BACKEND"] = "memory"
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-webhook-secret")

import asyncio
import itertools

import httpx
import pytest
from fastapi.testclient import TestClient

import app.channels.telegram as telegram
from app.main import APP_NAME, app, rate_limiter, session_service

client = TestClient(app)

_update_ids = itertools.count(1000)


def tg_update(text: str, chat_id: int = 111, chat_type: str = "private") -> dict:
    return {
        "update_id": next(_update_ids),
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
        },
    }


def post_update(update: dict, secret: str = "test-webhook-secret"):
    return client.post(
        "/webhooks/telegram",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )


class ApiRecorder:
    """Stands in for telegram._tg_api; records calls, optionally 400s HTML."""

    def __init__(self, fail_html: bool = False):
        self.calls: list[tuple[str, dict]] = []
        self.fail_html = fail_html

    async def __call__(self, method: str, payload: dict) -> httpx.Response:
        self.calls.append((method, payload))
        if self.fail_html and payload.get("parse_mode") == "HTML":
            return httpx.Response(400)
        return httpx.Response(200)

    def sent_texts(self) -> list[str]:
        return [p["text"] for m, p in self.calls if m == "sendMessage"]


@pytest.fixture
def api(monkeypatch) -> ApiRecorder:
    recorder = ApiRecorder()
    monkeypatch.setattr(telegram, "_tg_api", recorder)
    return recorder


@pytest.fixture
def fake_turn(monkeypatch):
    """Replaces the agent turn with a canned reply; returns a setter."""
    state = {"reply": "Here is an answer.", "sources": {}}

    async def _turn(runner, user_id, session_id, text):
        await asyncio.sleep(0)  # yield once, like a real turn would
        return state["reply"], dict(state["sources"])

    monkeypatch.setattr(telegram, "_run_turn", _turn)
    return state


# --- rendering ---


def test_render_bold_links_escape():
    rendered = telegram.render_telegram_html(
        "**Bold** & <tag> then [CDC](https://cdc.gov/a?x=1&y=2)"
    )
    assert "<b>Bold</b>" in rendered
    assert "&amp; &lt;tag&gt;" in rendered
    assert '<a href="https://cdc.gov/a?x=1&amp;y=2">CDC</a>' in rendered


def test_render_headers_and_bullets():
    rendered = telegram.render_telegram_html("## Section\n- item one\n* item two")
    assert "<b>Section</b>" in rendered
    assert "• item one" in rendered
    assert "• item two" in rendered


def test_split_message_short_is_single_chunk():
    assert telegram.split_message("hello") == ["hello"]


def test_split_message_prefers_newlines_and_respects_limit():
    text = "\n".join(f"line {i} " + "x" * 80 for i in range(100))
    chunks = telegram.split_message(text, limit=500)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks).count("line") == 100
    # splits land on line boundaries, so every chunk starts with a full line
    assert all(c.startswith("line") for c in chunks)


def test_split_message_hard_cuts_single_long_line():
    chunks = telegram.split_message("x" * 1200, limit=500)
    assert [len(c) for c in chunks] == [500, 500, 200]


def test_crisis_card_is_verbatim():
    card = telegram.crisis_card_text()
    assert telegram.CRISIS_RESOURCES["message"] in card
    for resource in telegram.CRISIS_RESOURCES["resources"]:
        assert resource["name"] in card
        assert resource["contact"] in card


# --- webhook auth / filtering ---


def test_webhook_404_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert post_update(tg_update("hi")).status_code == 404


def test_webhook_403_on_bad_secret():
    assert post_update(tg_update("hi"), secret="wrong").status_code == 403


def test_webhook_acks_malformed_json(api):
    response = client.post(
        "/webhooks/telegram",
        content=b"this is not json",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert api.calls == []


def test_webhook_ignores_non_text_and_group_chats(api, fake_turn):
    update = tg_update("hi")
    del update["message"]["text"]
    assert post_update(update).status_code == 200

    assert post_update(tg_update("hi", chat_type="group")).status_code == 200
    assert api.calls == []


def test_webhook_dedupes_update_id(api, fake_turn):
    update = tg_update("hello there", chat_id=222)
    assert post_update(update).status_code == 200
    sends_after_first = len(api.calls)
    assert post_update(update).status_code == 200
    assert len(api.calls) == sends_after_first


# --- conversation flows ---


def test_start_sends_welcome_with_privacy_disclosure(api, fake_turn):
    post_update(tg_update("/start", chat_id=333))
    texts = api.sent_texts()
    assert len(texts) == 1
    assert "30 days" in texts[0] and "/forget" in texts[0]


def test_reply_rendered_with_sources_footer(api, fake_turn):
    fake_turn["reply"] = "**Answer** here."
    fake_turn["sources"] = {"https://cdc.gov/x": "CDC"}
    post_update(tg_update("what is autism?", chat_id=444))
    html_sends = [p for m, p in api.calls
                  if m == "sendMessage" and p.get("parse_mode") == "HTML"]
    assert len(html_sends) == 1
    assert "<b>Answer</b>" in html_sends[0]["text"]
    assert '<a href="https://cdc.gov/x">CDC</a>' in html_sends[0]["text"]
    assert html_sends[0]["link_preview_options"] == {"is_disabled": True}


def test_typing_shown_during_turn(api, fake_turn):
    post_update(tg_update("hello", chat_id=1010))
    methods = [m for m, _ in api.calls]
    assert "sendChatAction" in methods
    assert methods.index("sendChatAction") < methods.index("sendMessage")


def test_crisis_card_sent_before_reply(api, fake_turn):
    post_update(tg_update("I want to hurt myself", chat_id=555))
    texts = api.sent_texts()
    assert len(texts) == 2
    assert "988" in texts[0]  # card first, verbatim, plain text
    assert texts[1] == telegram.render_telegram_html(fake_turn["reply"])


def test_html_rejection_falls_back_to_plain_text(monkeypatch, fake_turn):
    recorder = ApiRecorder(fail_html=True)
    monkeypatch.setattr(telegram, "_tg_api", recorder)
    fake_turn["reply"] = "**Answer** here."
    post_update(tg_update("hello", chat_id=666))
    plain = [p for m, p in recorder.calls
             if m == "sendMessage" and "parse_mode" not in p]
    assert plain and plain[-1]["text"] == "**Answer** here."


def test_rate_limit_sends_limit_message(api, fake_turn, monkeypatch):
    monkeypatch.setattr(rate_limiter, "_limit", 1)
    rate_limiter._counts.clear()
    post_update(tg_update("first", chat_id=777))
    post_update(tg_update("second", chat_id=777))
    assert api.sent_texts()[-1] == telegram.RATE_LIMIT_TEXT


def test_turn_failure_sends_apology_and_acks_200(api, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(telegram, "_run_turn", boom)
    response = post_update(tg_update("hello", chat_id=888))
    assert response.status_code == 200
    assert api.sent_texts()[-1] == telegram.ERROR_TEXT


def test_forget_deletes_the_chat_session(api, fake_turn):
    post_update(tg_update("hello", chat_id=999))  # creates tg-999
    session = asyncio.run(
        session_service.get_session(
            app_name=APP_NAME, user_id="tg-999", session_id="tg-999"
        )
    )
    assert session is not None
    post_update(tg_update("/forget", chat_id=999))
    session = asyncio.run(
        session_service.get_session(
            app_name=APP_NAME, user_id="tg-999", session_id="tg-999"
        )
    )
    assert session is None
    assert "deleted" in api.sent_texts()[-1].lower()
