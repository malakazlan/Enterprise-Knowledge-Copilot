# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (compose sets context: ..) so the image can
# bundle both the API and the built web app.

# ----- Frontend: build the static export (Node exists only in this stage) -----
FROM node:22-slim AS frontend

WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ----- Builder: install into an isolated virtualenv -----
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN python -m venv /opt/venv && pip install --upgrade pip

# Dependency metadata first for better layer caching.
COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app
# Ship with CPU-tier OCR and Office parsing so common enterprise documents
# work out of the box.
RUN pip install ".[ocr,office]"

# ----- Runtime: minimal, non-root, no Node -----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    FRONTEND_DIST=/app/frontend/out

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --from=builder /opt/venv /opt/venv
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini backend/pyproject.toml backend/README.md ./
COPY --from=frontend /fe/out ./frontend/out

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live').status==200 else 1)"

# One process per container; scale horizontally via orchestrator replicas.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
