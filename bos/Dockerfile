# syntax=docker/dockerfile:1.6
# =============================================================
# BOS Phase 1 - Dockerfile
# Single-image, local-only deployment. All persistence is in a named
# volume so workflows/audit/KB survive container restarts.
# =============================================================
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install -r requirements.txt

# App source
COPY app/ ./app/
COPY web/ ./web/
COPY knowledge_base/ ./knowledge_base/
COPY scripts/ ./scripts/
COPY pyproject.toml ./

# Storage mount points
RUN mkdir -p /app/app/data /app/app/data/chroma
VOLUME ["/app/app/data"]

EXPOSE 8000

# Healthcheck using the admin endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS -H "X-API-Key: $$BOS_API_KEY" http://localhost:8000/api/admin/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
