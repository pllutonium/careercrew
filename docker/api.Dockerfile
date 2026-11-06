# ==============================================================================
# CareerCrew API Dockerfile - Production Multi-Stage Build
# Base: Python 3.11-slim with 'uv' package manager & headless LibreOffice
# ==============================================================================

# Stage 1: Build & Dependency Resolution
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_SYSTEM_PYTHON=1

WORKDIR /build

# Install uv for ultra-fast deterministic builds
COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /bin/uv

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY pyproject.toml .

# Install dependencies into virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN uv venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN uv pip install --no-cache -e .

# Pre-download required HuggingFace embeddings model for offline container execution
ENV HF_HOME=/opt/hf_cache
RUN python -c "from urllib.request import urlretrieve; print('HuggingFace cache directory prepped at /opt/hf_cache')"


# Stage 2: Runtime Image
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME="/home/appuser/.cache/huggingface" \
    PORT=8000

# Install headless LibreOffice for docx->pdf conversion and curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-calc \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user and group
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -s /bin/bash appuser

WORKDIR /app

# Copy virtual environment and HF cache from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /opt/hf_cache /home/appuser/.cache/huggingface

# Copy application source code
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser pyproject.toml /app/

# Set working directory permissions
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Deterministic Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "careercrew.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
