# Backend — Enterprise Knowledge Copilot

FastAPI service: ingestion, hybrid retrieval, grounded generation, governance,
webhooks, connectors, SSO, and the MCP server. See the
[project README](../README.md) for the product overview.

## Layout

```
app/
├── main.py            Application factory; serves API + built web app
├── api/v1/            Versioned HTTP API (auth, documents, query, threads,
│                      collections, reviews, evals, webhooks, connectors, sso)
├── core/              Config, security, rate limiting, logging, middleware
├── models/            SQLAlchemy ORM models
├── schemas/           Pydantic request/response schemas
├── services/          Ingestion, retrieval, generation, access control,
│                      webhooks, SSO, evals
├── mcp/               MCP server (`ekc-mcp` console script)
├── db/                Async engine + session
└── workers/           Celery tasks
alembic/               Migrations (auto-applied on startup)
tests/                 Hermetic pytest suite (offline providers forced)
```

## Local development

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      POSIX: source .venv/bin/activate
pip install -e ".[dev,ocr,office,local,mcp]"
cp .env.example .env

uvicorn app.main:app --reload      # http://localhost:8000/docs
```

Optional extras: `ocr` (scanned PDFs/images), `office` (DOCX/PPTX/XLSX),
`local` (ONNX embeddings + cross-encoder reranker), `mcp` (agent tools).

## Quality gates

```bash
ruff check app tests        # lint
ruff format --check app tests
mypy app                    # strict type-check
pytest                      # hermetic tests
```
