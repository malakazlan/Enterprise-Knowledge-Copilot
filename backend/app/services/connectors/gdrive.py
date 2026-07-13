"""Google Drive connector: click-to-connect OAuth, idempotent sync.

Flow: the admin is redirected to Google's consent screen (drive.readonly);
the callback stores an ENCRYPTED refresh token on the connector. Sync lists
the configured folder (or full Drive), downloads new/changed files (Google
Docs/Sheets/Slides export to Office formats), and feeds them through the
same checksum-deduplicated ingestion as every other source.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 - URL, not a secret
_API = "https://www.googleapis.com/drive/v3"
_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_STATE_TTL_SECONDS = 600

# Google-native formats export to Office equivalents our parsers understand.
_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}

# Test seam: routes Google traffic into a mock.
_transport: httpx.AsyncBaseTransport | None = None


def gdrive_configured() -> bool:
    return bool(
        settings.gdrive_client_id and settings.gdrive_client_secret and settings.public_base_url
    )


def _require_configured() -> None:
    if not gdrive_configured():
        raise ServiceUnavailableError(
            "Google Drive is not configured. Set GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET "
            "and PUBLIC_BASE_URL."
        )


def redirect_uri() -> str:
    return f"{str(settings.public_base_url).rstrip('/')}/api/v1/connectors/gdrive/callback"


def make_state(connector_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "type": "gdrive-connect",
            "connector_id": str(connector_id),
            "iat": now,
            "exp": now + timedelta(seconds=_STATE_TTL_SECONDS),
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def read_state(state: str) -> uuid.UUID:
    try:
        claims = jwt.decode(
            state, settings.secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired connect state.") from exc
    if claims.get("type") != "gdrive-connect":
        raise AuthenticationError("Invalid connect state.")
    return uuid.UUID(str(claims["connector_id"]))


def authorization_url(connector_id: uuid.UUID) -> str:
    _require_configured()
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": settings.gdrive_client_id,
        "redirect_uri": redirect_uri(),
        "scope": _SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": make_state(connector_id),
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange the consent code; returns the refresh token ENCRYPTED."""
    _require_configured()
    assert settings.gdrive_client_secret is not None
    async with httpx.AsyncClient(timeout=20.0, transport=_transport) as client:
        response = await client.post(
            _TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
                "client_id": settings.gdrive_client_id,
                "client_secret": settings.gdrive_client_secret.get_secret_value(),
            },
        )
    if response.status_code != 200:
        raise AuthenticationError(f"Google code exchange failed ({response.status_code}).")
    body = response.json()
    refresh = body.get("refresh_token")
    if not refresh:
        raise AuthenticationError(
            "Google returned no refresh token — remove the app's prior grant at "
            "myaccount.google.com/permissions and connect again."
        )
    return encrypt_secret(refresh)


async def _access_token(encrypted_refresh: str) -> str:
    assert settings.gdrive_client_secret is not None
    async with httpx.AsyncClient(timeout=20.0, transport=_transport) as client:
        response = await client.post(
            _TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": decrypt_secret(encrypted_refresh),
                "client_id": settings.gdrive_client_id,
                "client_secret": settings.gdrive_client_secret.get_secret_value(),
            },
        )
    if response.status_code != 200:
        raise AuthenticationError(
            f"Google token refresh failed ({response.status_code}) — reconnect the provider."
        )
    return str(response.json()["access_token"])


async def list_files(
    encrypted_refresh: str, folder_id: str | None, max_files: int
) -> list[dict[str, Any]]:
    """Files visible to the grant, newest first, capped."""
    _require_configured()
    token = await _access_token(encrypted_refresh)
    query = "trashed = false"
    if folder_id:
        query += f" and '{folder_id}' in parents"

    files: list[dict[str, Any]] = []
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=30.0, transport=_transport) as client:
        while len(files) < max_files:
            params: dict[str, Any] = {
                "q": query,
                "fields": "nextPageToken, files(id, name, mimeType, size)",
                "pageSize": min(100, max_files - len(files)),
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(
                f"{_API}/files",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                raise ServiceUnavailableError(
                    f"Google Drive listing failed ({response.status_code})."
                )
            body = response.json()
            files.extend(body.get("files", []))
            page_token = body.get("nextPageToken")
            if not page_token:
                break
    return files[:max_files]


async def download_file(
    encrypted_refresh: str, file: dict[str, Any]
) -> tuple[str, str, bytes] | None:
    """(filename, content_type, data) — Google-native formats are exported;
    returns None for types we cannot ingest."""
    token = await _access_token(encrypted_refresh)
    file_id, name, mime = file["id"], file["name"], file.get("mimeType", "")

    async with httpx.AsyncClient(timeout=60.0, transport=_transport) as client:
        if mime in _EXPORTS:
            export_mime, extension = _EXPORTS[mime]
            response = await client.get(
                f"{_API}/files/{file_id}/export",
                params={"mimeType": export_mime},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                return None
            if not name.endswith(extension):
                name += extension
            return name, export_mime, response.content

        response = await client.get(
            f"{_API}/files/{file_id}",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            return None
        return name, mime or "application/octet-stream", response.content
