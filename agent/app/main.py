"""Autie agent service: FastAPI + ADK Runner, streaming chat over SSE.

Privacy constraint (docs/architecture.md §5): never log conversation text —
log metadata only (session id, latency, event counts).
"""

import asyncio
import json
import logging
import os
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from .agent import root_agent
from .auth import get_current_user
from .safety.crisis import CRISIS_RESOURCES, detect_crisis
from .safety.postcheck import scan_reply

logger = logging.getLogger("autie")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

APP_NAME = "autie"

# Firestore keeps sessions across Cloud Run scale-to-zero; memory is for tests.
if os.getenv("SESSIONS_BACKEND", "firestore") == "memory":
    session_service = InMemorySessionService()
else:
    from .sessions import FirestoreSessionService

    session_service = FirestoreSessionService(
        project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
        database=os.getenv("FIRESTORE_DATABASE", "(default)"),
    )
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

app = FastAPI(title="Autie agent service", version="0.1.0")

# Serializes concurrent sends on the same session within this instance (e.g.
# two tabs). Cross-instance races remain possible but are rare at this scale
# and concurrency setting; see docs/backlog.md.
_session_locks: dict[str, asyncio.Lock] = {}


def _session_lock(key: str) -> asyncio.Lock:
    if len(_session_locks) > 5000:  # unbounded-growth guard
        for stale_key in [k for k, v in _session_locks.items() if not v.locked()]:
            del _session_locks[stale_key]
    return _session_locks.setdefault(key, asyncio.Lock())


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


# Not /healthz: Google's frontend reserves that path on run.app domains and
# answers it with its own 404 before the request reaches the container.
@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/sessions/{session_id}")
async def session_history(
    session_id: str, user_id: str = Depends(get_current_user)
) -> dict:
    """Displayable history of one of the caller's own sessions (for reload restore)."""
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = []
    for event in session.events:
        if not (event.content and event.content.parts):
            continue
        text = "".join(part.text for part in event.content.parts if part.text)
        if not text:
            continue
        role = "user" if event.author == "user" else "assistant"
        messages.append({"role": role, "text": text})
    return {"session_id": session_id, "messages": messages}


@app.post("/api/chat")
async def chat(req: ChatRequest, user_id: str = Depends(get_current_user)) -> StreamingResponse:
    session_id = req.session_id or uuid.uuid4().hex

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if session is None:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    async def stream():
        started = time.monotonic()
        events = 0
        # First event tells the client which session to continue with.
        yield _sse({"type": "session", "session_id": session_id})
        # Deterministic safety pre-check: crisis resources are shown regardless
        # of what the model does, and the conversation stays open.
        if detect_crisis(req.message):
            logger.info("crisis pre-check triggered session=%s", session_id)
            yield _sse({"type": "crisis_resources", **CRISIS_RESOURCES})
        # url -> title, in first-use order; filled from tool responses so the
        # links are appended VERBATIM by code, never retyped by the model.
        sources: dict[str, str] = {}
        try:
            async with _session_lock(f"{user_id}:{session_id}"):
                new_message = types.Content(
                    role="user", parts=[types.Part(text=req.message)]
                )
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=new_message,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                ):
                    events += 1
                    if not (event.content and event.content.parts):
                        continue
                    for part in event.content.parts:
                        response = getattr(part, "function_response", None)
                        if response and response.name == "search_knowledge_base":
                            for excerpt in (response.response or {}).get("excerpts", []):
                                url = excerpt.get("source_url")
                                if url:
                                    sources.setdefault(
                                        url, excerpt.get("source_title") or url
                                    )
                        if not part.text:
                            continue
                        if event.partial:
                            yield _sse({"type": "text_delta", "text": part.text})
                        elif event.is_final_response():
                            scan_reply(part.text, session_id)
                            # Full final text; delta consumers may ignore it.
                            yield _sse({"type": "text_final", "text": part.text})
            if sources:
                footer = "**Sources:**\n" + "\n".join(
                    f"- [{title}]({url})" for url, title in sources.items()
                )
                yield _sse({"type": "text_final", "text": footer})
            yield _sse({"type": "done"})
            logger.info(
                "chat ok session=%s events=%d latency_ms=%d",
                session_id, events, int((time.monotonic() - started) * 1000),
            )
        except Exception:
            logger.exception("chat failed session=%s events=%d", session_id, events)
            yield _sse({
                "type": "error",
                "message": "Autie is temporarily unavailable. Please try again in a moment.",
            })

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
