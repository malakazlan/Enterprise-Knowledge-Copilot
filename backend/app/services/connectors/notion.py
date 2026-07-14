"""Notion connector: click-to-connect OAuth, pages exported as Markdown.

Flow mirrors Google Drive: the admin consents on Notion's grant screen, the
callback stores an ENCRYPTED workspace token (Notion tokens do not expire, so
there is no refresh dance). Sync walks the pages shared with the integration,
renders their blocks to Markdown, and feeds them through the same
checksum-deduplicated ingestion as every other source.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.services.connectors import oauth_state

_AUTH_ENDPOINT = "https://api.notion.com/v1/oauth/authorize"
_TOKEN_ENDPOINT = "https://api.notion.com/v1/oauth/token"  # noqa: S105 - URL, not a secret
_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"
_STATE_KIND = "notion-connect"
_MAX_BLOCK_DEPTH = 2

# Test seam: routes Notion traffic into a mock.
_transport: httpx.AsyncBaseTransport | None = None


def notion_configured() -> bool:
    return bool(
        settings.notion_client_id and settings.notion_client_secret and settings.public_base_url
    )


def _require_configured() -> None:
    if not notion_configured():
        raise ServiceUnavailableError(
            "Notion is not configured. Set NOTION_CLIENT_ID, NOTION_CLIENT_SECRET "
            "and PUBLIC_BASE_URL."
        )


def redirect_uri() -> str:
    return f"{str(settings.public_base_url).rstrip('/')}/api/v1/connectors/notion/callback"


def make_state(connector_id: uuid.UUID) -> str:
    return oauth_state.make_state(_STATE_KIND, connector_id)


def read_state(state: str) -> uuid.UUID:
    return oauth_state.read_state(_STATE_KIND, state)


def authorization_url(connector_id: uuid.UUID) -> str:
    _require_configured()
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": settings.notion_client_id,
        "redirect_uri": redirect_uri(),
        "owner": "user",
        "state": make_state(connector_id),
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange the consent code; returns the workspace token ENCRYPTED."""
    _require_configured()
    assert settings.notion_client_id is not None
    assert settings.notion_client_secret is not None
    async with httpx.AsyncClient(timeout=20.0, transport=_transport) as client:
        response = await client.post(
            _TOKEN_ENDPOINT,
            auth=(settings.notion_client_id, settings.notion_client_secret.get_secret_value()),
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
            },
        )
    if response.status_code != 200:
        raise AuthenticationError(f"Notion code exchange failed ({response.status_code}).")
    token = response.json().get("access_token")
    if not token:
        raise AuthenticationError("Notion returned no access token.")
    return encrypt_secret(str(token))


def _headers(encrypted_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {decrypt_secret(encrypted_token)}",
        "Notion-Version": _VERSION,
    }


async def list_pages(encrypted_token: str, max_pages: int) -> list[dict[str, Any]]:
    """Pages shared with the integration, most recently edited first, capped."""
    _require_configured()
    headers = _headers(encrypted_token)
    pages: list[dict[str, Any]] = []
    cursor: str | None = None
    async with httpx.AsyncClient(timeout=30.0, transport=_transport) as client:
        while len(pages) < max_pages:
            payload: dict[str, Any] = {
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": min(100, max_pages - len(pages)),
            }
            if cursor:
                payload["start_cursor"] = cursor
            response = await client.post(f"{_API}/search", json=payload, headers=headers)
            if response.status_code != 200:
                raise ServiceUnavailableError(
                    f"Notion page listing failed ({response.status_code})."
                )
            body = response.json()
            pages.extend(body.get("results", []))
            cursor = body.get("next_cursor")
            if not body.get("has_more") or not cursor:
                break
    return pages[:max_pages]


def page_title(page: dict[str, Any]) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            text = "".join(part.get("plain_text", "") for part in prop.get("title", []))
            if text.strip():
                return text.strip()
    return "Untitled"


def _rich_text(block_payload: dict[str, Any]) -> str:
    return "".join(part.get("plain_text", "") for part in block_payload.get("rich_text", []))


def _block_line(block: dict[str, Any]) -> str | None:
    kind = block.get("type", "")
    payload = block.get(kind, {})
    text = _rich_text(payload)
    if kind == "paragraph":
        return text or None
    if kind in ("heading_1", "heading_2", "heading_3"):
        return f"{'#' * int(kind[-1])} {text}" if text else None
    if kind == "bulleted_list_item":
        return f"- {text}"
    if kind == "numbered_list_item":
        return f"1. {text}"
    if kind == "to_do":
        mark = "x" if payload.get("checked") else " "
        return f"- [{mark}] {text}"
    if kind == "quote":
        return f"> {text}"
    if kind == "callout":
        return f"> {text}"
    if kind == "code":
        language = payload.get("language", "")
        return f"```{language}\n{text}\n```"
    if kind == "toggle":
        return text or None
    return None  # dividers, images, embeds, databases — nothing to index


async def _block_lines(
    client: httpx.AsyncClient, headers: dict[str, str], block_id: str, depth: int
) -> list[str] | None:
    lines: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        response = await client.get(
            f"{_API}/blocks/{block_id}/children", params=params, headers=headers
        )
        if response.status_code != 200:
            return None
        body = response.json()
        for block in body.get("results", []):
            line = _block_line(block)
            if line is not None:
                lines.append(line)
            if block.get("has_children") and depth < _MAX_BLOCK_DEPTH:
                children = await _block_lines(client, headers, block["id"], depth + 1)
                if children:
                    lines.extend(f"  {child}" for child in children)
        cursor = body.get("next_cursor")
        if not body.get("has_more") or not cursor:
            break
    return lines


def _safe_filename(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", title).strip() or "Untitled"


async def export_page(encrypted_token: str, page: dict[str, Any]) -> tuple[str, str, bytes] | None:
    """(filename, content_type, data) as Markdown; None if the page is unreadable."""
    headers = _headers(encrypted_token)
    title = page_title(page)
    async with httpx.AsyncClient(timeout=60.0, transport=_transport) as client:
        lines = await _block_lines(client, headers, page["id"], depth=0)
    if lines is None:
        return None
    markdown = f"# {title}\n\n" + "\n\n".join(lines) + "\n"
    return f"{_safe_filename(title)}.md", "text/markdown", markdown.encode("utf-8")
