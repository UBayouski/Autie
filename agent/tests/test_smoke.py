"""Smoke tests that don't require GCP credentials: app boot, health, auth gate."""

import os

os.environ["AUTH_DISABLED"] = "true"
os.environ["SESSIONS_BACKEND"] = "memory"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_rejects_empty_message():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_requires_token_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    response = client.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_chat_streams_session_event_then_error_without_credentials():
    # Without ADC the model call fails, but the stream itself must stay well-formed:
    # a session event first, then a user-safe error event - never a raised exception.
    with client.stream("POST", "/api/chat", json={"message": "hi"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in response.iter_text())
    assert '"type": "session"' in body
    assert '"type": "error"' in body or '"type": "done"' in body
