"""Tests for the hardening pass: rate limiting, delete-my-data, session TTL."""

import os

os.environ["AUTH_DISABLED"] = "true"
os.environ["SESSIONS_BACKEND"] = "memory"

import asyncio
import datetime

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import APP_NAME, app, session_service
from app.ratelimit import InMemoryRateLimiter
from app.sessions import _expire_at

client = TestClient(app)


def _seed_session(session_id: str) -> None:
    asyncio.run(
        session_service.create_session(
            app_name=APP_NAME, user_id="dev-user", session_id=session_id
        )
    )


# --- rate limiting ---


def test_rate_limiter_allows_within_limit_and_blocks_over():
    limiter = InMemoryRateLimiter(limit_per_hour=3)

    async def run():
        results = [await limiter.check("u1") for _ in range(4)]
        other = await limiter.check("u2")
        return results, other

    results, other = asyncio.run(run())
    assert results == [True, True, True, False]
    assert other is True  # per-uid, not global


def test_rate_limiter_zero_disables():
    limiter = InMemoryRateLimiter(limit_per_hour=0)
    assert asyncio.run(limiter.check("u1")) is True


def test_chat_returns_429_over_limit(monkeypatch):
    monkeypatch.setattr(main_module, "rate_limiter", InMemoryRateLimiter(1))
    first = client.post("/api/chat", json={"message": "hi"})
    assert first.status_code == 200
    second = client.post("/api/chat", json={"message": "hi again"})
    assert second.status_code == 429


# --- delete-my-data ---


def test_delete_session():
    _seed_session("del-one")
    assert client.get("/api/sessions/del-one").status_code == 200
    response = client.delete("/api/sessions/del-one")
    assert response.status_code == 200
    assert client.get("/api/sessions/del-one").status_code == 404


def test_delete_unknown_session_404():
    assert client.delete("/api/sessions/nope").status_code == 404


def test_delete_my_data_removes_all_sessions():
    _seed_session("mine-1")
    _seed_session("mine-2")
    response = client.delete("/api/me")
    assert response.status_code == 200
    assert response.json()["deleted_sessions"] >= 2
    assert client.get("/api/sessions/mine-1").status_code == 404
    assert client.get("/api/sessions/mine-2").status_code == 404


# --- session TTL ---


def test_expire_at_offsets_by_ttl_days():
    expire = _expire_at(0.0, 30)
    assert expire == datetime.datetime(1970, 1, 31, tzinfo=datetime.timezone.utc)


def test_expire_at_disabled_when_ttl_zero():
    assert _expire_at(0.0, 0) is None
