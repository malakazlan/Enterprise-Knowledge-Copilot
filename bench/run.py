"""Trust Bench: measures whether a RAG deployment answers groundedly and
refuses honestly.

Answerable questions score answer correctness (expected keywords), citation
presence, and citation targeting. Trap questions have NO answer in the corpus:
answering them at all is a false answer (a hallucination); refusing is correct.

Usage (against a running EKC deployment):
    python bench/run.py --base-url http://127.0.0.1:8000 \
        --email admin@example.com --password ...   # or --api-key ekc_...

Uploads bench/corpus/* (checksum-safe to re-run), waits for indexing, runs
bench/questions.jsonl, prints a Markdown report, writes JSON next to it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trust Bench runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--api-key", help="ekc_ API key (alternative to email/password)")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--questions", default=str(HERE / "questions.jsonl"))
    parser.add_argument("--corpus", default=str(HERE / "corpus"))
    parser.add_argument("--output", default=str(HERE / "results" / "latest.json"))
    parser.add_argument("--skip-upload", action="store_true")
    return parser.parse_args()


def auth_headers(client: httpx.Client, args: argparse.Namespace) -> dict[str, str]:
    if args.api_key:
        return {"Authorization": f"Bearer {args.api_key}"}
    if not (args.email and args.password):
        sys.exit("Provide --api-key or --email/--password.")
    response = client.post(
        "/api/v1/auth/login", json={"email": args.email, "password": args.password}
    )
    if response.status_code != 200:
        sys.exit(f"Login failed ({response.status_code}): {response.text[:200]}")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload_corpus(client: httpx.Client, headers: dict[str, str], corpus: Path) -> None:
    existing = {
        doc["filename"]
        for doc in client.get("/api/v1/documents?limit=200", headers=headers).json()
    }
    for path in sorted(corpus.glob("*.md")):
        if path.name in existing:
            print(f"  corpus: {path.name} already present")
            continue
        response = client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": (path.name, path.read_bytes(), "text/markdown")},
        )
        print(f"  corpus: {path.name} -> {response.status_code}")
    # Wait for ingestion to complete (eager mode finishes immediately).
    deadline = time.time() + 180
    while time.time() < deadline:
        docs = client.get("/api/v1/documents?limit=200", headers=headers).json()
        ours = [d for d in docs if d["filename"].startswith("meridian-")]
        if ours and all(d["status"] == "completed" for d in ours):
            return
        if any(d["status"] == "failed" for d in ours):
            sys.exit("Corpus ingestion failed; check the server logs.")
        time.sleep(2)
    sys.exit("Timed out waiting for corpus ingestion.")


def score_answerable(question: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    answer = (response.get("answer") or "").lower()
    citations = response.get("citations") or []
    keywords_ok = all(k.lower() in answer for k in question["expected_keywords"])
    cited_expected = any(
        question["expected_doc"] in (c.get("filename") or "") for c in citations
    )
    return {
        "answered": bool(response.get("answered")),
        "keywords_ok": keywords_ok,
        "cited": bool(citations),
        "cited_expected_doc": cited_expected,
        "grounded": bool(response.get("answered")) and keywords_ok and bool(citations),
        "confidence": response.get("confidence"),
    }


def score_trap(response: dict[str, Any]) -> dict[str, Any]:
    answered = bool(response.get("answered"))
    return {"answered": answered, "refused_correctly": not answered}


def main() -> None:
    args = parse_args()
    client = httpx.Client(base_url=args.base_url, timeout=120.0)
    headers = auth_headers(client, args)

    if not args.skip_upload:
        print("Uploading corpus…")
        upload_corpus(client, headers, Path(args.corpus))

    questions = [
        json.loads(line)
        for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    rows: list[dict[str, Any]] = []
    print(f"Running {len(questions)} questions…")
    for question in questions:
        payload: dict[str, Any] = {"query": question["question"]}
        if args.profile:
            payload["profile"] = args.profile
        started = time.perf_counter()
        response = client.post("/api/v1/query", headers=headers, json=payload)
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            sys.exit(f"Query failed ({response.status_code}): {response.text[:200]}")
        body = response.json()
        scored = (
            score_answerable(question, body)
            if question["type"] == "answerable"
            else score_trap(body)
        )
        rows.append({**question, **scored, "latency_ms": round(latency_ms)})
        marker = "PASS" if scored.get("grounded") or scored.get("refused_correctly") else "FAIL"
        print(f"  {marker} {question['id']} ({round(latency_ms)} ms)")

    answerable = [r for r in rows if r["type"] == "answerable"]
    traps = [r for r in rows if r["type"] == "trap"]

    def rate(items: list[dict[str, Any]], key: str) -> float:
        return sum(1 for r in items if r[key]) / len(items) if items else 0.0

    cited_rows = [r for r in answerable if r["answered"] and r["cited"]]
    confidences = [r["confidence"] for r in answerable if r["answered"] and r["confidence"]]
    metrics = {
        "answer_rate": rate(answerable, "answered"),
        "grounded_answer_rate": rate(answerable, "grounded"),
        "citation_doc_accuracy": rate(cited_rows, "cited_expected_doc"),
        "false_answer_rate": rate(traps, "answered"),
        "trap_refusal_rate": rate(traps, "refused_correctly"),
        "avg_confidence_when_answered": (
            round(statistics.mean(confidences), 3) if confidences else None
        ),
        "p50_latency_ms": round(statistics.median(r["latency_ms"] for r in rows)),
    }

    print("\n## Trust Bench results\n")
    print("| Metric | Value |")
    print("|---|---|")
    print(f"| Grounded answer rate (answerable) | {metrics['grounded_answer_rate']:.0%} |")
    print(f"| Answer rate (answerable) | {metrics['answer_rate']:.0%} |")
    print(f"| Citation targets the right document | {metrics['citation_doc_accuracy']:.0%} |")
    print(f"| **False answer rate (traps)** | **{metrics['false_answer_rate']:.0%}** |")
    print(f"| Trap refusal rate | {metrics['trap_refusal_rate']:.0%} |")
    print(f"| Avg confidence when answered | {metrics['avg_confidence_when_answered']} |")
    print(f"| p50 latency | {metrics['p50_latency_ms']} ms |")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"metrics": metrics, "rows": rows}, indent=2), encoding="utf-8"
    )
    print(f"\nDetails: {output}")


if __name__ == "__main__":
    main()
