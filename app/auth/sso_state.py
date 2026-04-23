"""Short-lived Redis state for OIDC login — PKCE verifier + nonce + return_to,
keyed by the opaque `state` value sent to the IdP. TTL 5 minutes."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

TTL_SECONDS = 300
_PREFIX = "sso:state:"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


async def begin(*, return_to: str | None = None) -> dict[str, Any]:
    state = uuid.uuid4().hex
    verifier, challenge = _pkce_pair()
    nonce = secrets.token_urlsafe(32)
    payload = {
        "state": state,
        "verifier": verifier,
        "challenge": challenge,
        "nonce": nonce,
        "return_to": return_to,
    }
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        await r.set(_PREFIX + state, json.dumps(payload), ex=TTL_SECONDS)
    finally:
        await r.aclose()
    return payload


async def consume(state: str) -> dict[str, Any] | None:
    """Single-shot read — deletes on return so a code can't be replayed."""
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        key = _PREFIX + state
        raw = await r.get(key)
        if raw is None:
            return None
        await r.delete(key)
        return json.loads(raw)
    finally:
        await r.aclose()
