# ── Stage 1: Build ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY packages/backend/pyproject.toml packages/backend/
COPY packages/backend/src/ packages/backend/src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ./packages/backend

# ── Stage 2: Production ───────────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL org.opencontainers.image.title="Forge" \
      org.opencontainers.image.description="The AI Execution Layer" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.licenses="MIT"

# Security: run as non-root
RUN groupadd -r forge && useradd -r -g forge -d /app forge

WORKDIR /app

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Create data and plugins directories
RUN mkdir -p /app/data /root/.forge/plugins && \
    chown -R forge:forge /app

USER forge

ENV FORGE_DB_URL=sqlite+aiosqlite:////app/data/forge.db \
    FORGE_HOST=0.0.0.0 \
    FORGE_PORT=8000 \
    FORGE_LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "forge.presentation.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--log-level", "info", \
     "--access-log"]
