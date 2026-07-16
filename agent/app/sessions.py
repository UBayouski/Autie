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

Retention (docs/architecture.md §5): session and event docs carry an
`expire_at` timestamp consumed by Firestore TTL policies on the `sessions` and
`events` collection groups. The session doc's expire_at refreshes on every
appended event; each event doc keeps the expire_at from its own write time, so
a conversation that stays active longer than the TTL sheds its oldest events
first (rolling window). Firestore deletes expired docs within ~24h of expiry.
"""

import datetime
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


def _expire_at(from_ts: float, ttl_days: float) -> Optional[datetime.datetime]:
    """TTL timestamp for a doc written at from_ts; None when TTL is off."""
    if ttl_days <= 0:
        return None
    return datetime.datetime.fromtimestamp(
        from_ts + ttl_days * 86400, tz=datetime.timezone.utc
    )


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
        ttl_days: float = 30.0,
    ):
        self._db = firestore.AsyncClient(project=project, database=database)
        self._root = root_collection
        self._ttl_days = ttl_days

    def _expire_at(self, from_ts: float) -> Optional[datetime.datetime]:
        return _expire_at(from_ts, self._ttl_days)

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
        session_doc: dict[str, Any] = {
            "app_name": app_name,
            "user_id": user_id,
            "state": scopes["session"],
            "create_time": now,
            "last_update_time": now,
        }
        if (expire_at := self._expire_at(now)) is not None:
            session_doc["expire_at"] = expire_at
        await self._session_ref(app_name, user_id, session_id).set(session_doc)

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
        if user_id is None:
            # The cross-user collection-group query needs a composite index on
            # (app_name) that we haven't created; fail loudly instead of at
            # query time if this path is ever exercised (docs/backlog.md).
            raise NotImplementedError(
                "list_sessions across all users requires a composite index on "
                "the 'sessions' collection group; create it before enabling "
                "this path."
            )
        query = self._user_ref(app_name, user_id).collection("sessions")

        sessions = []
        async for doc in query.stream():
            data = doc.to_dict()
            sessions.append(
                await self._merge_scoped_state(
                    app_name,
                    user_id,
                    Session(
                        app_name=app_name,
                        user_id=user_id,
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

    async def delete_user_data(self, *, app_name: str, user_id: str) -> int:
        """Deletes every session (with events) and the user doc for a uid.

        The delete-my-data path (docs/architecture.md §5). Returns the number
        of sessions deleted.
        """
        user_ref = self._user_ref(app_name, user_id)
        count = 0
        async for session_doc in user_ref.collection("sessions").stream():
            await self.delete_session(
                app_name=app_name, user_id=user_id, session_id=session_doc.id
            )
            count += 1
        await user_ref.delete()
        return count

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
        event_doc: dict[str, Any] = {
            "data": json.dumps(event.model_dump(mode="json", exclude_none=True)),
            "timestamp": event.timestamp,
        }
        expire_at = self._expire_at(event.timestamp)
        if expire_at is not None:
            event_doc["expire_at"] = expire_at
        await session_ref.collection("events").document(event_id).set(event_doc)

        updates: dict[str, Any] = {"last_update_time": event.timestamp}
        if expire_at is not None:
            updates["expire_at"] = expire_at
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
