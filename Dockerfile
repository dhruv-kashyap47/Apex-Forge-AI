# ─────────────────────────────────────────────
# ApexForge AI — Dockerfile
# Multi-stage: deps cached separately from code
# ─────────────────────────────────────────────

FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 1: Install Python deps ─────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Application ─────────────────────
FROM deps AS app
COPY . .

RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /home/appuser/.streamlit \
    && chown -R appuser:appuser /home/appuser/.streamlit

# Streamlit config
COPY .streamlit/config.toml /home/appuser/.streamlit/config.toml
ENV HOME=/home/appuser
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
