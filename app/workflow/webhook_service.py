"""Webhook management — regenerate hook_id, configure auth, verify incoming."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import Workflow


class WebhookAuthFailed(Exception):
    pass


class WebhookNotConfigured(Exception):
    pass


class WebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_hook_id(self, hook_id: str) -> Workflow | None:
        # O(n) scan over workflows with a webhook_config. Fine for 1b; add a
        # functional index on webhook_config->>'hook_id' if volume grows.
        rows = await self.db.execute(
            select(Workflow).where(Workflow.webhook_config.isnot(None))
        )
        for wf in rows.scalars().all():
            if (wf.webhook_config or {}).get("hook_id") == hook_id:
                return wf
        return None

    async def regenerate(
        self, wf_id: uuid.UUID, *, auth_type: str = "hmac",
    ) -> dict:
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise WebhookNotConfigured(str(wf_id))
        cfg = dict(wf.webhook_config or {})
        cfg["hook_id"] = uuid.uuid4().hex
        cfg["auth_type"] = auth_type
        if auth_type in ("bearer", "hmac"):
            cfg["secret"] = secrets.token_urlsafe(32)
        else:
            cfg.pop("secret", None)
        wf.webhook_config = cfg
        await self.db.flush()
        return cfg

    async def update_config(self, wf_id: uuid.UUID, patch: dict) -> dict:
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise WebhookNotConfigured(str(wf_id))
        cfg = dict(wf.webhook_config or {})
        for k in ("auth_type", "allowed_ips"):
            if k in patch:
                cfg[k] = patch[k]
        wf.webhook_config = cfg
        await self.db.flush()
        return cfg

    async def delete(self, wf_id: uuid.UUID) -> None:
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise WebhookNotConfigured(str(wf_id))
        wf.webhook_config = None
        await self.db.flush()

    @staticmethod
    def verify(
        cfg: dict,
        *,
        headers: dict,
        raw_body: bytes,
        client_ip: str,
    ) -> None:
        """Raise WebhookAuthFailed on any check failure. Returns None on success."""
        allowed = cfg.get("allowed_ips") or []
        if allowed and client_ip not in allowed:
            raise WebhookAuthFailed(f"IP {client_ip} not allowed")

        auth_type = cfg.get("auth_type", "none")
        if auth_type == "none":
            return

        secret = cfg.get("secret") or ""

        if auth_type == "bearer":
            auth = headers.get("authorization", "") or headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise WebhookAuthFailed("missing Bearer token")
            token = auth.removeprefix("Bearer ").strip()
            if not hmac.compare_digest(token, secret):
                raise WebhookAuthFailed("bearer token mismatch")
            return

        if auth_type == "hmac":
            sig = headers.get("x-signature", "") or headers.get("X-Signature", "")
            if not sig.startswith("sha256="):
                raise WebhookAuthFailed("missing X-Signature: sha256=...")
            expected = hmac.new(
                secret.encode(),
                raw_body + cfg.get("hook_id", "").encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(sig.removeprefix("sha256=").strip(), expected):
                raise WebhookAuthFailed("hmac signature mismatch")
            return

        raise WebhookAuthFailed(f"unknown auth_type: {auth_type}")
