"""Per-user rate limiting (docs/backlog.md §Hardening).

Anonymous Firebase sign-in makes uids free to mint, so this is an abuse cap,
not a security boundary: N requests per uid per clock hour. The Firestore
variant keeps the counter durable across Cloud Run scale-to-zero and shared
across instances (an in-memory counter would reset on every cold start, which
at scale-to-zero is most of the time). Failure mode is OPEN — a Firestore
hiccup must never take chat down.

Counter docs live in the `rate_limits` collection with an `expire_at` field so
the same Firestore TTL mechanism used for sessions cleans them up.
"""

import datetime
import logging
import time
from typing import Optional, Protocol

logger = logging.getLogger("autie")


class RateLimiter(Protocol):
    async def check(self, uid: str) -> bool:
        """Records one request for uid; True if it is within the limit."""
        ...


def _window(now: float) -> int:
    return int(now // 3600)


class InMemoryRateLimiter:
    """Per-process variant for tests and local development."""

    def __init__(self, limit_per_hour: int):
        self._limit = limit_per_hour
        self._counts: dict[tuple[str, int], int] = {}

    async def check(self, uid: str) -> bool:
        if self._limit <= 0:
            return True
        window = _window(time.time())
        for stale in [key for key in self._counts if key[1] != window]:
            del self._counts[stale]
        key = (uid, window)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] <= self._limit


class FirestoreRateLimiter:
    def __init__(
        self,
        limit_per_hour: int,
        project: Optional[str] = None,
        database: str = "(default)",
        collection: str = "rate_limits",
    ):
        from google.cloud import firestore

        self._limit = limit_per_hour
        self._db = firestore.AsyncClient(project=project, database=database)
        self._collection = collection

    async def check(self, uid: str) -> bool:
        if self._limit <= 0:
            return True
        from google.cloud import firestore

        window = _window(time.time())
        ref = self._db.collection(self._collection).document(f"{uid}:{window}")
        try:
            # Blind increment + read instead of a transaction: concurrent
            # requests can overshoot by a few, which is fine for an abuse cap.
            await ref.set(
                {
                    "uid": uid,
                    "count": firestore.Increment(1),
                    "expire_at": datetime.datetime.fromtimestamp(
                        (window + 2) * 3600, tz=datetime.timezone.utc
                    ),
                },
                merge=True,
            )
            snapshot = await ref.get()
            return (snapshot.get("count") or 0) <= self._limit
        except Exception:
            logger.warning("rate limiter unavailable, allowing request", exc_info=True)
            return True
