"""Firebase ID token verification for the chat endpoint.

Set AUTH_DISABLED=true for local development only — never in a deployed service.
"""

import os

from fastapi import Header, HTTPException


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


_firebase_ready = False


def _init_firebase() -> None:
    global _firebase_ready
    if _firebase_ready:
        return
    import firebase_admin

    if not firebase_admin._apps:
        # Uses Application Default Credentials on Cloud Run / gcloud ADC locally.
        firebase_admin.initialize_app()
    _firebase_ready = True


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """Returns the Firebase uid for the request, or raises 401."""
    if _auth_disabled():
        return "dev-user"

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    _init_firebase()
    from firebase_admin import auth as fb_auth

    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    return decoded["uid"]
