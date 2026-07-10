<div align="center">

# Enterprise Knowledge Copilot

**Production-grade RAG & Document Intelligence for regulated enterprises.**

Turn 10,000+ PDFs, contracts, SOPs, and manuals into a trustworthy, cited, auditable answer engine.

</div>

---

## Why this exists

Enterprises in healthcare, legal, finance, manufacturing, insurance, and government sit on
mountains of unstructured documents. Employees waste hours hunting through them, and generic
chatbots hallucinate answers no compliance team will accept.

**Enterprise Knowledge Copilot** is built for the constraints those industries actually have:

- **Every answer is cited** down to the document and page, or it is not returned.
- **Confidence is scored** and low-confidence answers are routed to **human review**.
- **Hallucinations are detected** by grounding each claim against retrieved evidence.
- **Everything is auditable** — who asked what, what was retrieved, what was answered.

## Core capabilities

| Area | What it does |
| --- | --- |
| **Ingestion** | LlamaParse (primary) → Docling (fallback) → OCR for scans; layout-aware parsing, metadata extraction, semantic chunking |
| **Retrieval** | Hybrid search — Pinecone dense vectors **+** BM25 sparse lexical, fused with Reciprocal Rank Fusion |
| **Reranking** | Cross-encoder / Cohere reranking of fused candidates for precision |
| **Generation** | Grounded answers with inline **source + page citations** |
| **Trust** | Per-answer **confidence score**, **hallucination detection**, **human review mode** |
| **Admin** | Dashboard for documents, ingestion jobs, review queue, usage analytics |
| **Security** | JWT auth, role-based access control (admin / reviewer / user), full audit trail |

## Architecture

```
                            ┌──────────────────────────────┐
        React + TS UI  ───► │           FastAPI            │
   (chat · admin · review)  │   REST + streaming (SSE)     │
                            └───────────────┬──────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              ▼                             ▼                             ▼
      ┌───────────────┐          ┌────────────────────┐         ┌────────────────┐
      │  Ingestion    │          │     Retrieval      │         │   Generation   │
      │ parse·OCR·    │          │ dense (Pinecone) + │         │ LLM · cite ·   │
      │ chunk·extract │          │ sparse (BM25) →RRF │         │ confidence ·   │
      │  (Celery)     │          │   → rerank         │         │ halluc. check  │
      └───────┬───────┘          └─────────┬──────────┘         └───────┬────────┘
              │                            │                            │
      ┌───────┴──────────┬─────────────────┴───────────┬────────────────┴────────┐
      ▼                  ▼                             ▼                          ▼
 ┌─────────┐      ┌────────────┐               ┌──────────────┐          ┌──────────────┐
 │ Postgres│      │   Redis    │               │   Pinecone   │          │ Object store │
 │metadata·│      │ cache·queue│               │ vector index │          │  raw files   │
 │audit·RBAC│     │  broker    │               └──────────────┘          └──────────────┘
 └─────────┘      └────────────┘
```

## Tech stack

**Backend** — Python · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · asyncpg · Alembic · Celery
**Data** — PostgreSQL · Redis · Pinecone
**AI** — LlamaParse · Docling · provider-abstracted LLM & embeddings · cross-encoder / Cohere reranking
**Frontend** — React 18 · TypeScript · Vite · Tailwind CSS · shadcn/ui · TanStack Query
**Ops** — Docker · Docker Compose · GitHub Actions · structlog · Prometheus

## Repository layout

```
Enterprise-Knowledge-Copilot/
├── backend/            FastAPI service, ingestion/retrieval/generation, workers
├── frontend/           React + TypeScript single-page app
├── infra/              Docker Compose, provisioning, deployment manifests
├── docs/               Architecture decision records and guides
└── .github/            CI/CD workflows
```

## Quickstart

> Full local stack (API, workers, Postgres, Redis) via Docker Compose.

```bash
# 1. Configure environment
cp backend/.env.example backend/.env    # then fill in secrets & provider keys

# 2. Bring up the stack
make up

# 3. API docs
open http://localhost:8000/docs
```

Local development without Docker is documented in [`docs/development.md`](docs/development.md).

## Status

This project is built in phases. Current progress is tracked in [`docs/roadmap.md`](docs/roadmap.md).

- [x] **Phase 0** — Foundation (service scaffold, config, observability, containerization, CI)
- [x] **Phase 1** — Data layer & authentication (models, migrations, JWT/RBAC)
- [ ] **Phase 2** — Ingestion pipeline (parse, OCR, chunk, embed, index)
- [ ] **Phase 3** — Hybrid retrieval & reranking
- [ ] **Phase 4** — Grounded generation (citations, confidence, hallucination detection)
- [ ] **Phase 5** — Human review & admin analytics
- [ ] **Phase 6** — Frontend application
- [ ] **Phase 7** — Test coverage, observability, documentation

## License

[MIT](LICENSE)
