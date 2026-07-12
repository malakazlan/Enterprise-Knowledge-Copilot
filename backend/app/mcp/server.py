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


@mcp.tool()
async def list_profiles() -> list[dict[str, Any]]:
    """List domain profiles with their full retrieval/generation settings.

    Use to compare strictness (confidence thresholds), chunking, and top-k
    when recommending a profile during setup.
    """
    profiles: list[dict[str, Any]] = await _call("GET", "/profiles")
    return profiles


@mcp.tool()
async def eval_create_dataset(
    name: str, description: str | None = None, profile: str | None = None
) -> dict[str, Any]:
    """Create a golden-question dataset for evaluating answer quality.

    Requires an admin-role API key.
    """
    payload: dict[str, Any] = {"name": name, "description": description, "profile": profile}
    data = await _call("POST", "/evals/datasets", payload)
    return {"dataset_id": data["id"], "name": data["name"], "profile": data["profile"]}


@mcp.tool()
async def eval_add_case(
    dataset_id: str,
    question: str,
    expected_keywords: list[str] | None = None,
    expected_page: int | None = None,
) -> dict[str, Any]:
    """Add a golden question to a dataset.

    `expected_keywords` are terms a correct answer's evidence must contain —
    ask the admin what a correct answer looks like and derive keywords.
    """
    payload: dict[str, Any] = {
        "question": question,
        "expected_keywords": expected_keywords or [],
        "expected_page": expected_page,
    }
    data = await _call("POST", f"/evals/datasets/{dataset_id}/cases", payload)
    return {"case_id": data["id"], "question": data["question"]}


@mcp.tool()
async def eval_run(dataset_id: str, profile: str | None = None) -> dict[str, Any]:
    """Run a dataset against the live pipeline; returns quality metrics.

    Pass `profile` to A/B-compare profiles on the same questions. Metrics:
    hit_rate, mrr, page_hit_rate, keyword_recall, citation_accuracy (0-1).
    """
    payload: dict[str, Any] = {"profile": profile} if profile else {}
    data = await _call("POST", f"/evals/datasets/{dataset_id}/run", payload)
    return {
        "run_id": data["id"],
        "profile": data["profile"],
        "case_count": data["case_count"],
        "metrics": data["metrics"],
    }


@mcp.tool()
async def review_queue(status: str = "pending", limit: int = 20) -> list[dict[str, Any]]:
    """List answers flagged for human review (status: pending|approved|rejected).

    Requires a reviewer- or admin-role API key.
    """
    data = await _call("GET", f"/reviews?status={status}&limit={max(1, min(limit, 200))}")
    return [
        {
            "id": r["id"],
            "question": r["query"],
            "confidence": r["confidence"],
            "profile": r["profile"],
            "created_at": r["created_at"],
        }
        for r in data
    ]


@mcp.prompt(name="setup-copilot")
def setup_copilot() -> str:
    """Interview the administrator and configure this deployment step by step."""
    return (
        "You are the setup copilot for a self-hosted Enterprise Knowledge "
        "Copilot deployment. Work through this checklist with the "
        "administrator, one step at a time, using the ekc tools:\n\n"
        "1. ORIENT - call deployment_stats and list_documents. Summarize what "
        "is already deployed (documents, queries, pending reviews).\n"
        "2. INTERVIEW - ask about their industry, how costly a wrong answer "
        "is (prefer declining vs. answering), and whether cloud AI providers "
        "are permitted or everything must stay on their servers.\n"
        "3. RECOMMEND A PROFILE - call list_profiles, compare thresholds to "
        "their risk tolerance, and recommend one. High-stakes domains (legal, "
        "healthcare, government) need high refuse/review thresholds.\n"
        "4. PROVIDERS - based on the cloud question, recommend .env settings: "
        "local-only (EMBEDDER_PROVIDER=hashing, LLM_PROVIDER=extractive, or "
        "Ollama for local LLM) versus cloud (openai/anthropic + qdrant). "
        "Explain that provider changes require editing .env and restarting - "
        "you cannot change them via tools.\n"
        "5. GOLDEN QUESTIONS - ask for 5-10 real questions their staff will "
        "ask, plus what a correct answer must mention. Create a dataset with "
        "eval_create_dataset, add each with eval_add_case (derive "
        "expected_keywords from the correct answers).\n"
        "6. EVALUATE - eval_run the dataset with the recommended profile. If "
        "metrics disappoint, try one alternative profile and compare. Explain "
        "results in plain language (hit_rate = how often the right document "
        "is found; keyword_recall = how often correct evidence appears).\n"
        "7. HAND OFF - summarize: chosen profile, .env recommendations, eval "
        "scores, and how to use the review queue. Never invent metrics - "
        "only report numbers returned by the tools; when a tool call fails, "
        "show the error and continue."
    )


@mcp.tool()
async def get_context(task: str, max_tokens: int = 2000) -> dict[str, Any]:
    """Assemble a token-budgeted context pack for a task.

    Returns ranked, deduplicated passages with [Source: file, p.N] provenance
    headers, cut to the budget — inject the `context` string into your prompt
    and cite the sources to the user.
    """
    data = await _call(
        "POST", "/context", {"task": task, "max_tokens": max(100, min(max_tokens, 16000))}
    )
    return {
        "context": data["context"],
        "tokens_used": data["tokens_used"],
        "sources": [{"filename": s["filename"], "page": s["page_number"]} for s in data["sources"]],
    }


@mcp.tool()
async def write_knowledge(
    title: str,
    content: str,
    source: str | None = None,
    verify_in_days: int | None = None,
) -> dict[str, Any]:
    """Deposit a knowledge entry (something learned worth keeping).

    The entry becomes retrievable within seconds and is attributed to
    `source` (your agent/workflow name). Set `verify_in_days` when the fact
    can go stale so humans re-verify it in time. Requires a reviewer- or
    admin-role API key.
    """
    payload: dict[str, Any] = {"title": title, "content": content}
    if source:
        payload["source"] = source
    if verify_in_days:
        payload["verify_in_days"] = verify_in_days
    data = await _call("POST", "/knowledge", payload)
    return {
        "document_id": data["id"],
        "filename": data["filename"],
        "status": data["status"],
        "verify_by": data["verify_by"],
    }


def main() -> None:
    """Console-script entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
