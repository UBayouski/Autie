"""Telegram channel adapter: POST /webhooks/telegram.

First messaging channel — chosen as the capability proof for the adapter
pattern, not for US reach (docs/future-integrations.md §Messaging channels).

Design notes:
- Caller auth is the webhook secret Telegram echoes back in the
  X-Telegram-Bot-Api-Secret-Token header (set at setWebhook time), NOT
  Firebase — this route must stay off the Firebase auth dependency.
- Identity: platform chat id maps to internal uid "tg-<chat_id>" with one
  rolling session per chat, so session TTL and the hourly rate limit apply
  unchanged.
- Safety parity: the deterministic crisis card is sent as its own message,
  verbatim and BEFORE the model reply, exactly like the web SSE path.
- No streaming: the update is processed within the webhook request (Cloud
  Run bills/keeps CPU for the request; a Cloud Tasks hop is the upgrade
  path if turn latency ever exceeds Telegram's patience). Telegram retries
  slow/failed deliveries, so updates are deduped by update_id and the
  handler answers 200 even on internal errors to avoid retry storms.
- Rendering: model markdown is converted to Telegram HTML (parse_mode=HTML;
  MarkdownV2 escaping is deliberately avoided). If Telegram rejects the
  entities, the reply is re-sent as plain text — delivery beats formatting.
- Group chats are ignored: 1:1 only, matching the privacy posture.

Privacy constraint (docs/architecture.md §5) applies: log metadata only,
never conversation text.
"""

import asyncio
import html
import logging
import os
import re
import secrets
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from ..safety.crisis import CRISIS_RESOURCES, detect_crisis
from ..safety.postcheck import scan_reply

logger = logging.getLogger("autie.telegram")

TELEGRAM_MAX_MESSAGE = 4096
_INPUT_MAX = 4000  # matches ChatRequest.message max_length

RATE_LIMIT_TEXT = "You've reached the hourly message limit. Please try again later."
ERROR_TEXT = "Autie is temporarily unavailable. Please try again in a moment."

WELCOME_TEXT = (
    "Hi! I'm Autie. Whether you're autistic or neurodivergent yourself, a "
    "parent or caregiver, a family member, or a friend — I'm here to help "
    "you find nearby services and support, make sense of resources, and get "
    "plain-language answers backed by trusted sources.\n\n"
    "A note on privacy: your messages travel through Telegram's servers and "
    "stay in your Telegram history; Autie keeps its own copy of the "
    "conversation for up to 30 days. Send /forget any time to delete Autie's "
    "copy. Please don't share identifying details like medical record numbers."
    "\n\n"
    "Autie shares information, not medical advice. If you're in crisis, call "
    "or text 988 (US)."
)


# --- Telegram Bot API client (module-level so tests can monkeypatch _tg_api) ---

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=15)
    return _http


async def _tg_api(method: str, payload: dict) -> httpx.Response:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    return await _client().post(
        f"https://api.telegram.org/bot{token}/{method}", json=payload
    )


async def _send(chat_id: int, text: str, as_html: bool = False) -> bool:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        # Sources footers would otherwise unfurl a preview per link.
        "link_preview_options": {"is_disabled": True},
    }
    if as_html:
        payload["parse_mode"] = "HTML"
    response = await _tg_api("sendMessage", payload)
    if response.status_code != 200:
        logger.warning(
            "sendMessage failed chat=%s status=%s html=%s",
            chat_id, response.status_code, as_html,
        )
    return response.status_code == 200


# --- rendering ---

_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_HEADER_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^(\s*)[-*]\s+", re.MULTILINE)


def render_telegram_html(markdown_text: str) -> str:
    """Converts the model's markdown subset to Telegram HTML.

    Escapes first, then rewrites links/bold/headers/bullets. Anything the
    model emits beyond that subset degrades to visible plain text, which is
    acceptable; the plain-text fallback in _send_reply covers hard failures.
    """
    text = html.escape(markdown_text, quote=False)
    text = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _HEADER_RE.sub(r"<b>\1</b>", text)
    text = _BULLET_RE.sub(r"\1• ", text)
    return text


def split_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE) -> list[str]:
    """Splits at newlines under Telegram's per-message limit (hard cut if a
    single line exceeds it)."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip("\n"))
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def crisis_card_text() -> str:
    """Plain-text crisis card. Resource strings are served VERBATIM from
    CRISIS_RESOURCES; only layout glue is added here."""
    lines = [CRISIS_RESOURCES["message"], ""]
    for resource in CRISIS_RESOURCES["resources"]:
        lines.append(
            f"• {resource['name']} — {resource['contact']} ({resource['note']})"
        )
    return "\n".join(lines)


async def _keep_typing(chat_id: int) -> None:
    """Shows "typing…" for the whole turn: Telegram expires the indicator
    after ~5s, so it needs refreshing until the reply goes out (which clears
    it). Runs as a task; cancelled when the turn finishes."""
    try:
        while True:
            await _tg_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        raise
    except Exception:
        return  # cosmetic — a send hiccup must not surface anywhere


async def _send_reply(chat_id: int, markdown_text: str) -> None:
    """Sends a model reply: HTML per chunk, plain-text fallback per chunk."""
    rendered = render_telegram_html(markdown_text)
    if len(rendered) <= TELEGRAM_MAX_MESSAGE:
        if await _send(chat_id, rendered, as_html=True):
            return
        for chunk in split_message(markdown_text):
            await _send(chat_id, chunk)
        return
    # Long reply: chunk the raw markdown so an HTML tag can't straddle a cut,
    # rendering each chunk independently.
    for chunk in split_message(markdown_text, limit=TELEGRAM_MAX_MESSAGE - 512):
        rendered_chunk = render_telegram_html(chunk)
        if not await _send(chat_id, rendered_chunk, as_html=True):
            await _send(chat_id, chunk)


# --- agent turn (non-streaming; mirrors the source collection in main.chat) ---


async def _run_turn(
    runner, user_id: str, session_id: str, text: str
) -> tuple[str, dict[str, str]]:
    """Runs one agent turn; returns (final reply text, url -> title sources)."""
    finals: list[str] = []
    sources: dict[str, str] = {}
    new_message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            response = getattr(part, "function_response", None)
            if response and response.name == "search_knowledge_base":
                for excerpt in (response.response or {}).get("excerpts", []):
                    url = excerpt.get("source_url")
                    if url:
                        sources.setdefault(url, excerpt.get("source_title") or url)
            if part.text and event.is_final_response():
                scan_reply(part.text, session_id)
                finals.append(part.text)
    return "\n\n".join(finals), sources


# --- webhook ---

# update_id -> first-seen time; Telegram redelivers updates it considers
# unacknowledged (e.g. while a long turn is still running).
_seen_updates: dict[int, float] = {}


def _already_seen(update_id: int) -> bool:
    now = time.time()
    if len(_seen_updates) > 500:
        for stale in [k for k, t in _seen_updates.items() if now - t > 600]:
            del _seen_updates[stale]
    if update_id in _seen_updates:
        return True
    _seen_updates[update_id] = now
    return False


def create_telegram_router(
    *, runner, session_service, rate_limiter, session_lock, app_name: str
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/telegram")
    async def telegram_webhook(request: Request) -> dict:
        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
        if not (os.getenv("TELEGRAM_BOT_TOKEN") and secret):
            raise HTTPException(status_code=404, detail="Channel not configured")
        header = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not secrets.compare_digest(header, secret):
            raise HTTPException(status_code=403, detail="Bad webhook secret")

        try:
            update = await request.json()
        except Exception:
            # Telegram retries non-200s; an unparseable body won't parse on
            # retry either, so ACK and drop it.
            return {"ok": True}
        update_id = update.get("update_id")
        if update_id is not None and _already_seen(update_id):
            return {"ok": True}

        # Text messages in private chats only; everything else is ACKed and
        # dropped (stickers, photos, edits, group chats, channel posts).
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        if not chat_id or not text or chat.get("type") != "private":
            return {"ok": True}
        text = text[:_INPUT_MAX]

        started = time.monotonic()
        uid = f"tg-{chat_id}"
        session_id = f"tg-{chat_id}"
        try:
            if text.startswith("/start"):
                await _send(chat_id, WELCOME_TEXT)
                return {"ok": True}
            if text.startswith("/forget"):
                deleted = await _forget(session_service, app_name, uid)
                await _send(
                    chat_id,
                    f"Done — deleted Autie's copy of {deleted} conversation(s). "
                    "Your Telegram history is yours to clear separately.",
                )
                logger.info("telegram forget ok uid=%s sessions=%d", uid, deleted)
                return {"ok": True}

            if not await rate_limiter.check(uid):
                await _send(chat_id, RATE_LIMIT_TEXT)
                return {"ok": True}

            # Deterministic safety pre-check: card goes out first, verbatim,
            # regardless of what the model does. Same guarantee as the web.
            if detect_crisis(text):
                logger.info("crisis pre-check triggered session=%s", session_id)
                await _send(chat_id, crisis_card_text())

            session = await session_service.get_session(
                app_name=app_name, user_id=uid, session_id=session_id
            )
            if session is None:
                await session_service.create_session(
                    app_name=app_name, user_id=uid, session_id=session_id
                )

            typing = asyncio.create_task(_keep_typing(chat_id))
            try:
                async with session_lock(f"{uid}:{session_id}"):
                    reply, sources = await _run_turn(runner, uid, session_id, text)
            finally:
                typing.cancel()
            if sources:
                reply += "\n\n**Sources:**\n" + "\n".join(
                    f"- [{title}]({url})" for url, title in sources.items()
                )
            if reply:
                await _send_reply(chat_id, reply)
            logger.info(
                "telegram ok session=%s latency_ms=%d",
                session_id, int((time.monotonic() - started) * 1000),
            )
        except Exception:
            logger.exception("telegram turn failed session=%s", session_id)
            await _send(chat_id, ERROR_TEXT)
        # Always 200: Telegram retries non-200s, and a retry of a failing
        # update would just fail again.
        return {"ok": True}

    return router


async def _forget(session_service, app_name: str, uid: str) -> int:
    """Delete-my-data parity for the Telegram identity."""
    if hasattr(session_service, "delete_user_data"):
        return await session_service.delete_user_data(app_name=app_name, user_id=uid)
    listed = await session_service.list_sessions(app_name=app_name, user_id=uid)
    for session in listed.sessions:
        await session_service.delete_session(
            app_name=app_name, user_id=uid, session_id=session.id
        )
    return len(listed.sessions)
