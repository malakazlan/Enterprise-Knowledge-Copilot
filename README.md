<div align="center">

# Enterprise Knowledge Copilot

**Open-source, self-hosted, agent-ready knowledge platform — every answer cited, scored, and governed.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![CI](https://github.com/malakazlan/Enterprise-Knowledge-Copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/malakazlan/Enterprise-Knowledge-Copilot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](backend/pyproject.toml)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](frontend/package.json)

</div>

Enterprises sit on thousands of PDFs, contracts, SOPs, and manuals — and employees waste hours searching them. Generic chatbots hallucinate answers no compliance team will accept, and SaaS RAG means shipping sensitive documents to someone else's cloud.

**Enterprise Knowledge Copilot** is the alternative you run yourself: a complete retrieval-augmented answering platform where every answer cites the exact document and page, carries a confidence score, and — when the evidence isn't there — **declines instead of guessing**. Humans review what the system isn't sure about. Agents consume it as tools. Nothing leaves your servers.

## What it does

**Ask, with receipts.** Streamed chat answers with inline `[1]` citations that jump to the highlighted passage in the source document. Persistent conversation threads. A composite confidence score (retrieval × groundedness × citations) on every answer.

**Refuse, on the record.** Below a per-domain confidence threshold, the system flags the answer for human review or refuses outright — and every refusal is logged with its reason. Reviewers approve or reject flagged answers with notes; the audit trail records who asked, what was answered, from which page, and who signed off.

**Ingest what enterprises actually have.** PDFs (with automatic CPU OCR for scans), Word / PowerPoint / Excel, images, Markdown, text. Structure-aware chunking keeps paragraphs intact and stamps every chunk with its section breadcrumb. A folder connector syncs a mounted share or drop directory idempotently — cron it and the corpus stays current.

**Control who sees what.** Collections put an access boundary around documents, enforced *inside* the retrieval pipeline (both search channels), not filtered after the fact. Membership is managed in the UI; revocation takes effect on the next query.

**Plug in your agents and apps.**
- **MCP server** (`ekc-mcp`) — Claude Desktop/Code or any MCP client gets `ask`, `search`, and admin tools, plus a `setup-copilot` prompt that interviews an admin and configures the deployment conversationally
- **REST API** — headless usage with role-scoped API keys (`X-API-Key`), batch endpoint for pipeline workloads, SSE streaming
- **Webhooks** — HMAC-signed pushes on refusals, review flags, resolutions, and ingestion events, with retry + backoff

**Prove the quality.** Golden-question datasets and an evaluation harness (hit rate, MRR, page accuracy, keyword recall, citation accuracy) run against the live pipeline — compare domain profiles A/B before trusting a change.

**Sign in your way.** Email/password (first account becomes admin) or OIDC single sign-on — Microsoft Entra, Google Workspace, Okta, Keycloak — enabled by four environment variables. Rate limiting guards auth (per IP) and query endpoints (per principal).

## Runs fully local — cloud optional

Every provider is a configuration choice behind the same port:

| Layer | Local (zero API keys) | Cloud / self-hosted |
|---|---|---|
| Embeddings | BGE via ONNX on CPU (`fastembed`) | OpenAI |
| Reranking | ONNX cross-encoder | (lexical fallback) |
| Answering | Extractive (conservative, no LLM) | OpenAI, Anthropic, Ollama, vLLM |
| Vector store | In-memory | Qdrant |
| OCR | RapidOCR (CPU) | GPU adapters planned |

The fully-local tier does real semantic search with no external calls after a one-time model download — air-gapped deployments work.

## Quickstart

```bash
git clone https://github.com/malakazlan/Enterprise-Knowledge-Copilot.git
cd Enterprise-Knowledge-Copilot
docker compose -f infra/docker-compose.yml up -d
```

Open **http://localhost:8000** — the first account you register is the administrator. Upload a document, ask a question, click the citation.

The image bundles the web app, API, migrations, OCR, and Office parsing. Interactive API reference at `/docs`; a zero-build fallback console at `/console`.

### Local development

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # POSIX: source .venv/bin/activate
pip install -e ".[dev,ocr,office,local,mcp]"
uvicorn app.main:app --reload

# frontend (dev server; production is a static export served by the API)
cd frontend
npm ci && npm run dev
```

Quality gates: `ruff check`, `ruff format --check`, `mypy` (strict), `pytest` (170+ hermetic tests — no network, no external services).

## Configuration essentials

Everything is environment-driven (see `backend/.env.example`):

```bash
# Providers
LLM_PROVIDER=extractive|openai|anthropic|ollama
EMBEDDER_PROVIDER=fastembed|openai|hashing
RERANKER_PROVIDER=onnx|lexical
VECTOR_STORE_PROVIDER=qdrant|memory
OCR_PROVIDER=rapidocr|none

# Domain behaviour (thresholds, chunking, top-k) — 7 built-in profiles:
# legal, finance, healthcare, government, manufacturing, insurance, general

# OIDC SSO (optional)
OIDC_ISSUER=https://accounts.google.com
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...
OIDC_REDIRECT_URL=https://your-host/api/v1/auth/oidc/callback
```

## Connect an agent (MCP)

```jsonc
// Claude Desktop / Claude Code MCP config
{
  "command": "ekc-mcp",
  "env": { "EKC_URL": "https://kb.your-company.internal", "EKC_API_KEY": "ekc_..." }
}
```

Agents get grounded, cited answers with machine-readable trust signals — `answered: false` means the corpus lacks evidence, so workflows can branch to a human instead of acting on a guess.

## Security posture

- Passwords hashed; JWT sessions with refresh rotation; API keys stored as SHA-256 hashes, shown once
- Role-based access (admin / reviewer / user) on every endpoint; document ACLs enforced at retrieval time
- Frontend ships as a static export served by the API — no Node.js process in production, CSP blocks all external origins, `npm audit` clean
- Rate limiting on auth and query; OIDC tokens validated against provider JWKS with nonce binding
- Webhook deliveries HMAC-SHA256 signed

## License

[Apache-2.0](LICENSE)
