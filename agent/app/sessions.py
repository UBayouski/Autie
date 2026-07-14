"""Firestore-backed ADK session service.

ADK 2.x ships InMemory (dies with the instance), Database (SQLAlchemy - needs
Cloud SQL), and VertexAi (Agent Engine pricing) session services. None fit a
scale-to-zero Cloud Run + Firestore stack, so this implements BaseSessionService
on Firestore directly (docs/architecture.md §2).

Layout (root collection "adk"):
    adk/{app_name}                                  -> {app_state}
    adk/{app_name}/users/{user_id}                  -> {user_state}
    adk/{app_name}/users/{user_id}/sessions/{sid}   -> {state, app_name, user_id,
                                                        create_time, last_update_time}
    .../sessions/{sid}/events/{event_id}            -> {data: json str, timestamp}

Events are stored as JSON strings: Firestore rejects nested arrays, which model
content (parts, function calls) can legally contain.
"""

import json
import time
import uuid
from typing import Any, Optional

from google.adk.events.event import Event
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import (
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.state import State
from google.cloud import firestore


def _split_state(state: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Splits a state dict into app/user/session scopes; temp: keys are dropped."""
    out: dict[str, dict[str, Any]] = {"app": {}, "user": {}, "session": {}}
    for key, value in (state or {}).items():
        if key.startswith(State.APP_PREFIX):
            out["app"][key.removeprefix(State.APP_PREFIX)] = value
        elif key.startswith(State.USER_PREFIX):
            out["user"][key.removeprefix(State.USER_PREFIX)] = value
        elif not key.startswith(State.TEMP_PREFIX):
            out["session"][key] = value
    return out


class FirestoreSessionService(BaseSessionService):
    def __init__(
        self,
        project: Optional[str] = None,
        database: str = "(default)",
        root_collection: str = "adk",
    ):
        self._db = firestore.AsyncClient(project=project, database=database)
        self._root = root_collection

    def _app_ref(self, app_name: str):
        return self._db.collection(self._root).document(app_name)

    def _user_ref(self, app_name: str, user_id: str):
        return self._app_ref(app_name).collection("users").document(user_id)

    def _session_ref(self, app_name: str, user_id: str, session_id: str):
        return self._user_ref(app_name, user_id).collection("sessions").document(session_id)

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        session_id = session_id.strip() if session_id and session_id.strip() else uuid.uuid4().hex
        scopes = _split_state(state)
        now = time.time()

        if scopes["app"]:
            await self._app_ref(app_name).set({"app_state": scopes["app"]}, merge=True)
        if scopes["user"]:
            await self._user_ref(app_name, user_id).set(
                {"user_state": scopes["user"]}, merge=True
            )
        await self._session_ref(app_name, user_id, session_id).set({
            "app_name": app_name,
            "user_id": user_id,
            "state": scopes["session"],
            "create_time": now,
            "last_update_time": now,
        })

        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=scopes["session"],
            last_update_time=now,
        )
        return await self._merge_scoped_state(app_name, user_id, session)

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        doc = await self._session_ref(app_name, user_id, session_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()

        events_query = self._session_ref(app_name, user_id, session_id).collection("events")
        if config and config.after_timestamp:
            events_query = events_query.where("timestamp", ">=", config.after_timestamp)
        if config and config.num_recent_events is not None:
            if config.num_recent_events == 0:
                events: list[Event] = []
            else:
                docs = [
                    d
                    async for d in events_query.order_by(
                        "timestamp", direction=firestore.Query.DESCENDING
                    )
                    .limit(config.num_recent_events)
                    .stream()
                ]
                events = [Event.model_validate(json.loads(d.get("data"))) for d in reversed(docs)]
        else:
            events = [
                Event.model_validate(json.loads(d.get("data")))
                async for d in events_query.order_by("timestamp").stream()
            ]

        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=data.get("state", {}),
            events=events,
            last_update_time=data.get("last_update_time", 0.0),
        )
        return await self._merge_scoped_state(app_name, user_id, session)

    async def _merge_scoped_state(
        self, app_name: str, user_id: str, session: Session
    ) -> Session:
        app_doc, user_doc = await self._app_ref(app_name).get(), None
        user_doc = await self._user_ref(app_name, user_id).get()
        if app_doc.exists:
            for key, value in (app_doc.to_dict().get("app_state") or {}).items():
                session.state[State.APP_PREFIX + key] = value
        if user_doc.exists:
            for key, value in (user_doc.to_dict().get("user_state") or {}).items():
                session.state[State.USER_PREFIX + key] = value
        return session

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        if user_id is not None:
            query = self._user_ref(app_name, user_id).collection("sessions")
        else:
            query = self._db.collection_group("sessions").where("app_name", "==", app_name)

        sessions = []
        async for doc in query.stream():
            data = doc.to_dict()
            sessions.append(
                await self._merge_scoped_state(
                    app_name,
                    data["user_id"],
                    Session(
                        app_name=app_name,
                        user_id=data["user_id"],
                        id=doc.id,
                        state=data.get("state", {}),
                        last_update_time=data.get("last_update_time", 0.0),
                    ),
                )
            )
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        session_ref = self._session_ref(app_name, user_id, session_id)
        async for event_doc in session_ref.collection("events").stream():
            await event_doc.reference.delete()
        await session_ref.delete()

    async def get_user_state(self, *, app_name: str, user_id: str) -> dict[str, Any]:
        doc = await self._user_ref(app_name, user_id).get()
        if not doc.exists:
            return {}
        return dict(doc.to_dict().get("user_state") or {})

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event
        # Updates the in-memory session (state delta, temp trimming) first.
        event = await super().append_event(session, event)
        session.last_update_time = event.timestamp

        event_id = event.id or uuid.uuid4().hex
        session_ref = self._session_ref(session.app_name, session.user_id, session.id)
        await session_ref.collection("events").document(event_id).set({
            "data": json.dumps(event.model_dump(mode="json", exclude_none=True)),
            "timestamp": event.timestamp,
        })

        updates: dict[str, Any] = {"last_update_time": event.timestamp}
        if event.actions and event.actions.state_delta:
            scopes = _split_state(event.actions.state_delta)
            if scopes["app"]:
                await self._app_ref(session.app_name).set(
                    {"app_state": scopes["app"]}, merge=True
                )
            if scopes["user"]:
                await self._user_ref(session.app_name, session.user_id).set(
                    {"user_state": scopes["user"]}, merge=True
                )
            for key, value in scopes["session"].items():
                updates[f"state.{key}"] = value
        await session_ref.update(updates)
        return event
