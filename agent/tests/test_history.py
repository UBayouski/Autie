"""Tests for the session history endpoint."""

import os

os.environ["AUTH_DISABLED"] = "true"
os.environ["SESSIONS_BACKEND"] = "memory"

import asyncio

from fastapi.testclient import TestClient
from google.adk.events.event import Event
from google.genai import types

from app.main import APP_NAME, app, session_service

client = TestClient(app)


def test_history_404_for_unknown_session():
    response = client.get("/api/sessions/does-not-exist")
    assert response.status_code == 404


def test_history_returns_displayable_messages():
    async def seed():
        session = await session_service.create_session(
            app_name=APP_NAME, user_id="dev-user", session_id="hist-test"
        )
        await session_service.append_event(
            session,
            Event(
                author="user",
                content=types.Content(role="user", parts=[types.Part(text="hello")]),
            ),
        )
        await session_service.append_event(
            session,
            Event(
                author="autie",
                content=types.Content(role="model", parts=[types.Part(text="hi there")]),
            ),
        )

    asyncio.run(seed())

    response = client.get("/api/sessions/hist-test")
    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "hi there"},
    ]
