"""OIDC authentication provider.

Supports Authorization Code + PKCE (S256). Config comes from runtime
SystemSettings (admin-editable). First login auto-provisions the user;
subsequent logins re-sync role + department from the IdP's group claims.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.providers.base import AuthResult, BaseAuthProvider
from app.core.runtime_config import get_runtime_config

log = logging.getLogger(__name__)

_CACHE_TTL = 3600.0
_discovery_cache: dict[str, dict[str, Any]] = {}
_jwks_cache: dict[str, dict[str, Any]] = {}


async def _discover(issuer: str) -> dict:
    entry = _discovery_cache.get(issuer)
    if entry and entry["_expires"] > time.time():
        return entry
    async with httpx.AsyncClient(timeout=8.0) as cli:
        r = await cli.get(issuer.rstrip("/") + "/.well-known/openid-configuration")
    r.raise_for_status()
    data = r.json()
    data["_expires"] = time.time() + _CACHE_TTL
    _discovery_cache[issuer] = data
    return data


async def _jwks(issuer: str, jwks_uri: str) -> dict:
    entry = _jwks_cache.get(issuer)
    if entry and entry["_expires"] > time.time():
        return entry
    async with httpx.AsyncClient(timeout=8.0) as cli:
        r = await cli.get(jwks_uri)
    r.raise_for_status()
    data = r.json()
    data["_expires"] = time.time() + _CACHE_TTL
    _jwks_cache[issuer] = data
    return data


async def _read_sso_config(db: AsyncSession) -> dict:
    cfg = await get_runtime_config(db)
    return (cfg or {}).get("sso") or {}


async def _exchange_code(cfg, discovery, code, verifier) -> dict | None:
    async with httpx.AsyncClient(timeout=8.0) as cli:
        try:
            r = await cli.post(
                discovery["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": cfg["redirect_uri"],
                    "client_id": cfg["client_id"],
                    "client_secret": cfg.get("client_secret") or "",
                    "code_verifier": verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as e:
            log.warning("sso token exchange failed: %s", e)
            return None
    if r.status_code != 200:
        log.warning(
            "sso token endpoint returned %s: %s", r.status_code, r.text[:200]
        )
        return None
    return r.json()


async def _verify_id_token(cfg, discovery, id_token, nonce) -> dict | None:
    try:
        jwks = await _jwks(cfg["issuer"], discovery["jwks_uri"])
        claims = jwt.decode(
            id_token,
            jwks,
            audience=cfg["client_id"],
            issuer=cfg["issuer"].rstrip("/"),
            options={"verify_at_hash": False},
        )
    except Exception as e:  # noqa: BLE001
        log.warning("id_token decode failed: %s", e)
        return None
    if nonce and claims.get("nonce") and claims["nonce"] != nonce:
        log.warning("id_token nonce mismatch")
        return None
    return claims


def _map_role(cfg: dict, claims: dict) -> UserRole | None:
    role_map: dict = cfg.get("role_map") or {}
    groups = claims.get(cfg.get("group_claim") or "groups") or []
    if isinstance(groups, str):
        groups = [groups]
    for g in groups:
        mapped = role_map.get(g)
        if mapped:
            try:
                return UserRole(mapped)
            except ValueError:
                log.warning("SSO role_map yielded invalid UserRole: %s", mapped)
    return None


def _map_department(cfg: dict, claims: dict) -> str | None:
    dept_map: dict = cfg.get("dept_map") or {}
    groups = claims.get(cfg.get("group_claim") or "groups") or []
    if isinstance(groups, str):
        groups = [groups]
    for g in groups:
        if g in dept_map:
            return dept_map[g]
    return None


async def _upsert_user(db: AsyncSession, cfg: dict, claims: dict) -> User:
    sub = claims.get("sub")
    email = claims.get("email") or f"sso-{sub}@example.invalid"
    name = claims.get("preferred_username") or claims.get("name") or email

    # Try (auth_provider="oidc", external_id=sub) first — most stable key.
    user = (await db.execute(
        select(User).where(
            User.auth_provider == "oidc",
            User.external_id == str(sub),
        )
    )).scalar_one_or_none()

    if user is None:
        # Fallback: link an existing local account with the same email.
        existing = (await db.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if existing is not None:
            existing.auth_provider = "oidc"
            existing.external_id = str(sub)
            user = existing
        else:
            user = User(
                username=name,
                email=email,
                hashed_password="",  # SSO-only — local login path checks this
                auth_provider="oidc",
                external_id=str(sub),
                is_active=True,
            )
            db.add(user)

    # Role re-sync on every login — IdP is source of truth when a mapping
    # exists. When no mapping matches, leave the stored role alone.
    mapped_role = _map_role(cfg, claims)
    if mapped_role is not None:
        user.role = mapped_role
    await db.flush()

    dept_name = _map_department(cfg, claims)
    if dept_name:
        from app.department.service import DepartmentService
        await DepartmentService(db).ensure_user_membership(user.id, dept_name)
        await db.flush()

    return user


class OIDCAuthProvider(BaseAuthProvider):
    name = "oidc"
    auto_provision = True

    async def authenticate(
        self, db: AsyncSession, credentials: dict,
    ) -> AuthResult:
        cfg = await _read_sso_config(db)
        if not cfg.get("enabled"):
            return AuthResult(None, reason="SSO disabled")

        code = credentials.get("code")
        verifier = credentials.get("verifier")
        nonce = credentials.get("nonce")
        if not (code and verifier):
            return AuthResult(None, reason="Missing code/verifier")

        try:
            discovery = await _discover(cfg["issuer"])
        except Exception as e:  # noqa: BLE001
            return AuthResult(None, reason=f"discovery failed: {e}")

        token_payload = await _exchange_code(cfg, discovery, code, verifier)
        if token_payload is None:
            return AuthResult(None, reason="code exchange failed")

        id_token = token_payload.get("id_token")
        if not id_token:
            return AuthResult(None, reason="IdP returned no id_token")

        claims = await _verify_id_token(cfg, discovery, id_token, nonce)
        if claims is None:
            return AuthResult(None, reason="id_token verification failed")

        user = await _upsert_user(db, cfg, claims)
        return AuthResult(user)
