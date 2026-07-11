"""OIDC single sign-on endpoints (browser redirect flow)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.deps import DbSession
from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.ratelimit import limit_auth
from app.core.security import create_access_token, create_refresh_token
from app.services import sso

router = APIRouter(tags=["sso"])


class SsoStatus(BaseModel):
    enabled: bool
    provider: str


@router.get("/status", response_model=SsoStatus, summary="Is SSO configured?")
async def status() -> SsoStatus:
    return SsoStatus(enabled=sso.oidc_enabled(), provider=settings.oidc_provider_name)


@router.get(
    "/login",
    dependencies=[Depends(limit_auth)],
    summary="Redirect the browser to the identity provider",
)
async def login() -> RedirectResponse:
    return RedirectResponse(await sso.build_authorization_url(), status_code=307)


@router.get(
    "/callback",
    dependencies=[Depends(limit_auth)],
    summary="Identity provider redirect target",
)
async def callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        raise AuthenticationError(f"SSO sign-in failed: {error or 'missing code/state'}.")
    user = await sso.handle_callback(db, code, state)
    subject = str(user.id)
    # Tokens travel in the URL fragment: the browser keeps fragments out of
    # request lines and logs; the login page stores them and cleans the URL.
    fragment = (
        f"sso_access={create_access_token(subject)}&sso_refresh={create_refresh_token(subject)}"
    )
    return RedirectResponse(f"/login/#{fragment}", status_code=307)
