"""Tests for eval metrics and the end-to-end evaluation harness."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.user import User, UserRole
from app.services.evals.metrics import aggregate, keyword_recall, page_hit, reciprocal_rank

EVALS = "/api/v1/evals"
DOCUMENTS = "/api/v1/documents"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

SAFETY_DOC = (
    b"# Site Safety Manual\n\n"
    b"All workers must wear a helmet at all times on the construction site.\n\n"
    b"\x0c"  # form feed -> page break
    b"Fire extinguishers are checked every month by the safety officer."
)
FINANCE_DOC = b"# Expense Policy\n\nInvoices must be submitted before the 5th of each month."


# --- metric units ---


def test_reciprocal_rank() -> None:
    assert reciprocal_rank(["a", "b", "c"], "a") == 1.0
    assert reciprocal_rank(["a", "b", "c"], "c") == 1.0 / 3
    assert reciprocal_rank(["a", "b"], "zzz") == 0.0
    assert reciprocal_rank([], "a") == 0.0


def test_page_hit() -> None:
    ranked = [("doc1", 1), ("doc1", 2), ("doc2", None)]
    assert page_hit(ranked, "doc1", 2) is True
    assert page_hit(ranked, "doc1", 3) is False
    assert page_hit(ranked, "doc2", 1) is False


def test_keyword_recall() -> None:
    assert keyword_recall("Workers must wear a HELMET on site", ["helmet", "site"]) == 1.0
    assert keyword_recall("Workers must wear a helmet", ["helmet", "goggles"]) == 0.5
    assert keyword_recall(None, ["helmet"]) == 0.0
    assert keyword_recall("anything", []) == 0.0


def test_aggregate_judges_only_scored_cases() -> None:
    results = [
        {  # fully judged, perfect
            "reciprocal_rank": 1.0,
            "page_hit": True,
            "answered": True,
            "citation_hit": True,
            "keyword_recall": 1.0,
            "confidence": 0.9,
            "grounded_ratio": 1.0,
        },
        {  # retrieval-only case (no keywords/pages)
            "reciprocal_rank": 0.5,
            "page_hit": None,
            "answered": False,
            "citation_hit": False,
            "keyword_recall": None,
            "confidence": 0.2,
            "grounded_ratio": 0.0,
        },
    ]
    metrics = aggregate(results)
    assert metrics["cases"] == 2
    assert metrics["hit_rate"] == 1.0  # both had rank > 0
    assert metrics["mrr"] == 0.75
    assert metrics["page_hit_rate"] == 1.0  # only one case judgeable
    assert metrics["answered_rate"] == 0.5
    assert metrics["citation_accuracy"] == 0.5
    assert metrics["keyword_recall"] == 1.0  # only one case judgeable
    assert metrics["avg_confidence"] == 0.55


def test_aggregate_empty() -> None:
    metrics = aggregate([])
    assert metrics["cases"] == 0
    assert metrics["hit_rate"] is None
    assert metrics["mrr"] is None


# --- end-to-end harness ---


async def _upload(client: AsyncClient, headers: dict[str, str], name: str, data: bytes) -> str:
    resp = await client.post(
        DOCUMENTS, headers=headers, files={"file": (name, data, "text/markdown")}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["document"]["id"])


async def test_eval_harness_end_to_end(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")

    safety_id = await _upload(client, headers, "safety.md", SAFETY_DOC)
    await _upload(client, headers, "expenses.md", FINANCE_DOC)

    # Build the golden dataset
    dataset = await client.post(
        EVALS + "/datasets",
        headers=headers,
        json={"name": "smoke", "description": "smoke set", "profile": "general"},
    )
    assert dataset.status_code == 201, dataset.text
    dataset_id = dataset.json()["id"]

    good_case = await client.post(
        f"{EVALS}/datasets/{dataset_id}/cases",
        headers=headers,
        json={
            "question": "Who must wear a helmet on the construction site?",
            "expected_document_id": safety_id,
            "expected_page": 1,
            "expected_keywords": ["helmet", "workers"],
        },
    )
    assert good_case.status_code == 201
    impossible_case = await client.post(
        f"{EVALS}/datasets/{dataset_id}/cases",
        headers=headers,
        json={"question": "quantum banana smoothie recipe", "expected_keywords": ["banana"]},
    )
    assert impossible_case.status_code == 201

    detail = await client.get(f"{EVALS}/datasets/{dataset_id}", headers=headers)
    assert len(detail.json()["cases"]) == 2

    # Run the harness against the live pipeline
    run = await client.post(f"{EVALS}/datasets/{dataset_id}/run", headers=headers, json={})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["profile"] == "general"
    assert body["case_count"] == 2

    metrics = body["metrics"]
    # Case 1 is retrievable and answerable with the offline stack:
    assert metrics["hit_rate"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["page_hit_rate"] == 1.0
    assert metrics["citation_accuracy"] == 1.0
    # Case 2 must be refused -> answered_rate is 0.5, not 1.0
    assert metrics["answered_rate"] == 0.5
    assert metrics["keyword_recall"] == 0.5  # helmet case 1.0, banana case 0.0

    per_case = {r["question"]: r for r in body["results"]}
    banana = per_case["quantum banana smoothie recipe"]
    assert banana["answered"] is False
    assert banana["refusal_reason"] == "insufficient_evidence"

    runs = await client.get(f"{EVALS}/datasets/{dataset_id}/runs", headers=headers)
    assert len(runs.json()) == 1


async def test_eval_profile_override_and_errors(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")

    created = await client.post(EVALS + "/datasets", headers=headers, json={"name": "ds"})
    dataset_id = created.json()["id"]

    # Run with an explicit profile override
    run = await client.post(
        f"{EVALS}/datasets/{dataset_id}/run", headers=headers, json={"profile": "legal"}
    )
    assert run.status_code == 200
    assert run.json()["profile"] == "legal"

    # Unknown profile -> 404; unknown dataset -> 404
    bad = await client.post(
        f"{EVALS}/datasets/{dataset_id}/run", headers=headers, json={"profile": "nope"}
    )
    assert bad.status_code == 404
    missing = await client.get(
        f"{EVALS}/datasets/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert missing.status_code == 404

    # Delete cleans up
    deleted = await client.delete(f"{EVALS}/datasets/{dataset_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"{EVALS}/datasets/{dataset_id}", headers=headers)).status_code == 404


async def test_evals_are_admin_only(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    member = await auth_headers("member@example.com")
    assert (await client.get(EVALS + "/datasets", headers=member)).status_code == 403
    assert (await client.get(EVALS + "/datasets")).status_code == 401
