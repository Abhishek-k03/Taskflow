# taskflow/api/auth.py

"""API key authentication.

Disabled when no keys are configured, so existing deployments and the test
suite keep working - turning it on is a deliberate act, not something that
happens the moment this module exists.

Only mutating routes are guarded. Health and readiness stay open because
probes cannot carry credentials, and the JSON metrics the dashboard polls
are read-only.
"""

import secrets
from typing import Optional

from fastapi import Header, HTTPException, Request, WebSocket

API_KEY_HEADER = "X-API-Key"


def _configured_keys(app) -> list[str]:
    return getattr(app.state, "api_keys", []) or []


def _matches(candidate: str, keys: list[str]) -> bool:
    # compare_digest rather than == so a wrong key cannot be recovered by
    # timing how long the rejection took.
    return any(secrets.compare_digest(candidate, key) for key in keys)


async def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    keys = _configured_keys(request.app)
    if not keys:
        return  # auth not configured

    if not x_api_key or not _matches(x_api_key, keys):
        raise HTTPException(
            status_code=401,
            detail=f"A valid {API_KEY_HEADER} header is required",
        )


async def websocket_key_is_valid(websocket: WebSocket) -> bool:
    """Browsers cannot set headers on `new WebSocket()`, so the socket is
    authenticated with a ?token= query parameter instead - checked before
    the connection is accepted."""
    keys = _configured_keys(websocket.app)
    if not keys:
        return True

    token = websocket.query_params.get("token")
    return bool(token) and _matches(token, keys)
