"""MCP server: lets Claude (or any MCP client) use an EKC deployment as tools.

Runs on the operator's machine and talks to the deployment's REST API with an
API key — the server itself holds no data and enforces nothing; the API's
authentication and RBAC apply unchanged.

Configuration (environment):
    EKC_URL      Base URL of the deployment, e.g. https://kb.firm.internal
    EKC_API_KEY  API key created in the web app (role decides what tools work)

Claude Desktop / Claude Code registration:
    {"command": "ekc-mcp", "env": {"EKC_URL": "...", "EKC_API_KEY": "ekc_..."}}
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "enterprise-knowledge-copilot",
    instructions=(
        "Tools for a self-hosted Enterprise Knowledge Copilot deployment. "
        "Use `ask` for grounded, cited answers; treat `answered=false` as the "
        "corpus genuinely lacking evidence — do not fill the gap from memory. "
        "Use `search` for raw passages when you want to reason over evidence "
        "yourself, and cite filenames and pages to the user."
    ),
)


# Test seam: lets the suite route requests into an in-process ASGI app.
_transport: httpx.AsyncBaseTransport | None = None


def _client() -> httpx.AsyncClient:
    url = os.environ.get("EKC_URL", "").rstrip("/")
    key = os.environ.get("EKC_API_KEY", "")
    if not url or not key:
        raise RuntimeError("Set EKC_URL and EKC_API_KEY to use this MCP server.")
    return httpx.AsyncClient(
        base_url=f"{url}/api/v1",
        headers={"X-API-Key": key},
        timeout=60.0,
        transport=_transport,
    )


async def _call(method: str, path: str, json: dict[str, Any] | None = None) -> Any:
    async with _client() as client:
        response = await client.request(method, path, json=json)
        if response.status_code >= 400:
            detail: Any = response.text
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except ValueError:
                detail = response.text  # non-JSON error body
            raise RuntimeError(f"EKC API error {response.status_code}: {detail}")
        return response.json()


@mcp.tool()
async def ask(question: str, profile: str | None = None) -> dict[str, Any]:
    """Ask the knowledge base a question; answers are grounded and cited.

    Returns the answer text with [n] citation markers, the cited sources
    (filename, page, snippet), a 0-1 confidence score, and `answered`. When
    `answered` is false the corpus lacks evidence — report that honestly.
    """
    payload: dict[str, Any] = {"query": question}
    if profile:
        payload["profile"] = profile
    data = await _call("POST", "/query", payload)
    return {
        "answered": data["answered"],
        "answer": data["answer"],
        "refusal_reason": data["refusal_reason"],
        "confidence": data["confidence"],
        "needs_review": data["needs_review"],
        "profile": data["profile"],
        "citations": [
            {
                "marker": c["marker"],
                "filename": c["filename"],
                "page": c["page_number"],
                "snippet": c["snippet"],
            }
            for c in data["citations"]
        ],
    }


@mcp.tool()
async def search(query: str, top_k: int = 8, profile: str | None = None) -> list[dict[str, Any]]:
    """Retrieve the most relevant passages (hybrid dense+keyword search).

    Returns raw passages with provenance — use when you want the evidence
    itself rather than a synthesized answer.
    """
    payload: dict[str, Any] = {"query": query, "top_k": max(1, min(top_k, 50))}
    if profile:
        payload["profile"] = profile
    data = await _call("POST", "/search", payload)
    return [
        {
            "filename": r["filename"],
            "page": r["page_number"],
            "content": r["content"],
            "score": r["score"],
            "document_id": r["document_id"],
        }
        for r in data["results"]
    ]


@mcp.tool()
async def list_documents() -> list[dict[str, Any]]:
    """List documents in the knowledge base (name, pages, status, id)."""
    data = await _call("GET", "/documents?limit=200")
    return [
        {
            "id": d["id"],
            "filename": d["filename"],
            "pages": d["page_count"],
            "status": d["status"],
            "created_at": d["created_at"],
        }
        for d in data
    ]


@mcp.tool()
async def deployment_stats() -> dict[str, Any]:
    """Deployment statistics: corpus size, answer rate, pending reviews.

    Requires an admin-role API key.
    """
    stats: dict[str, Any] = await _call("GET", "/admin/stats")
    return stats


def main() -> None:
    """Console-script entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
