"""Confluence connector: API-token auth, pages exported as Markdown.

Atlassian Cloud uses per-user API tokens (id.atlassian.com → Security → API
tokens), so there is no OAuth dance: the admin pastes site URL, email, and
token once; the token is stored ENCRYPTED and never returned by the API.
Sync lists pages (optionally limited to spaces), converts their storage-format
XHTML to Markdown-ish text, and feeds them through checksum-deduplicated
ingestion like every other source.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import httpx

from app.core.crypto import decrypt_secret
from app.core.exceptions import ServiceUnavailableError

# Test seam: routes Confluence traffic into a mock.
_transport: httpx.AsyncBaseTransport | None = None

_PAGE_SIZE = 50
_HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}
_BREAKS = {"p", "div", "table", "tr", "ul", "ol", "blockquote", "pre"}


class _StorageToText(HTMLParser):
    """Confluence storage-format XHTML → plain Markdown-ish text (stdlib only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if tag in _HEADINGS:
            self.parts.append(f"\n\n{_HEADINGS[tag]}")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")
        elif tag in _BREAKS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _HEADINGS or tag in _BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def storage_to_markdown(xhtml: str) -> str:
    parser = _StorageToText()
    parser.feed(xhtml)
    return parser.text()


def _safe_filename(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", title).strip() or "Untitled"


async def list_pages(
    base_url: str,
    email: str,
    encrypted_token: str,
    space_keys: list[str],
    max_pages: int,
) -> list[dict[str, Any]]:
    """Current pages with their storage bodies, capped across all spaces."""
    auth = (email, decrypt_secret(encrypted_token))
    base = base_url.rstrip("/")
    spaces: list[str | None] = list(space_keys) or [None]

    pages: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0, transport=_transport, auth=auth) as client:
        for space in spaces:
            start = 0
            while len(pages) < max_pages:
                params: dict[str, Any] = {
                    "type": "page",
                    "status": "current",
                    "limit": min(_PAGE_SIZE, max_pages - len(pages)),
                    "start": start,
                    "expand": "body.storage,space",
                }
                if space:
                    params["spaceKey"] = space
                response = await client.get(f"{base}/rest/api/content", params=params)
                if response.status_code != 200:
                    raise ServiceUnavailableError(
                        f"Confluence listing failed ({response.status_code}) — check the "
                        "site URL, email, and API token."
                    )
                body = response.json()
                results = body.get("results", [])
                pages.extend(results)
                if len(results) < params["limit"]:
                    break
                start += len(results)
            if len(pages) >= max_pages:
                break
    return pages[:max_pages]


def export_page(page: dict[str, Any]) -> tuple[str, str, bytes] | None:
    """(filename, content_type, data) as Markdown; None if the page has no body."""
    title = str(page.get("title") or "Untitled")
    space = str(page.get("space", {}).get("key") or "").strip()
    xhtml = page.get("body", {}).get("storage", {}).get("value") or ""
    text = storage_to_markdown(xhtml)
    if not text:
        return None
    markdown = f"# {title}\n\n{text}\n"
    prefix = f"{space} - " if space else ""
    return f"{prefix}{_safe_filename(title)}.md", "text/markdown", markdown.encode("utf-8")
