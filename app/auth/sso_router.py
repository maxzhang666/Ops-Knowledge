"""SSO login / callback / public config routes."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.providers.oidc import _discover, _read_sso_config
from app.auth.service import AuthService
from app.auth.sso_state import begin, consume
from app.core.database import get_db

router = APIRouter(prefix="/auth/sso", tags=["auth-sso"])


@router.get("/config")
async def public_config(db: AsyncSession = Depends(get_db)):
    """Non-sensitive shape consumed by the login page — tells the UI whether
    to render the SSO button and what label to use. Secrets never leak here."""
    cfg = await _read_sso_config(db)
    if not cfg.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "button_label": cfg.get("button_label", "使用 SSO 登录"),
    }


@router.get("/login")
async def login(
    return_to: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _read_sso_config(db)
    if not cfg.get("enabled"):
        raise HTTPException(400, "SSO not enabled")
    try:
        discovery = await _discover(cfg["issuer"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"IdP discovery failed: {e}")

    state = await begin(return_to=return_to)
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg.get("scopes") or "openid profile email",
        "state": state["state"],
        "code_challenge": state["challenge"],
        "code_challenge_method": "S256",
        "nonce": state["nonce"],
    }
    return RedirectResponse(
        url=f"{discovery['authorization_endpoint']}?{urlencode(params)}",
        status_code=302,
    )


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    saved = await consume(state)
    if saved is None:
        raise HTTPException(400, "Invalid or expired state")

    svc = AuthService(db)
    user = await svc.authenticate_via_provider("oidc", {
        "code": code,
        "verifier": saved["verifier"],
        "nonce": saved["nonce"],
    })
    if user is None:
        raise HTTPException(401, "SSO authentication failed")

    tokens = svc.create_tokens(user)
    return_to = saved.get("return_to") or "/"
    # Tokens go in URL fragment — never captured by server / proxy access logs.
    # Frontend login callback page parses fragment, stores tokens, then
    # replaces URL to clean it from history.
    fragment = urlencode({
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
    })
    return RedirectResponse(url=f"{return_to}#{fragment}", status_code=302)
