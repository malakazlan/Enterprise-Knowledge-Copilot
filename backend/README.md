# Backend — Enterprise Knowledge Copilot

FastAPI service for ingestion, hybrid retrieval, and grounded generation.
See the [project README](../README.md) for the full architecture and roadmap.

## Layout

```
app/
├── main.py            Application factory + ASGI entrypoint
├── api/v1/            Versioned HTTP API (routers + endpoints)
├── core/              Config, logging, exceptions, metrics, middleware
├── models/            SQLAlchemy ORM models            (phase 1)
├── schemas/           Pydantic request/response schemas (phase 1)
├── services/          Ingestion, retrieval, generation (phases 2–4)
├── db/                Async engine + session           (phase 1)
└── workers/           Celery tasks                     (phase 2)
tests/                 Pytest suite
```

## Local development

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      POSIX: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

uvicorn app.main:app --reload      # http://localhost:8000/docs
```

## Quality gates

```bash
ruff check app tests      # lint
mypy app                  # type-check
pytest                    # tests
```
