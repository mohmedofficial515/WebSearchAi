# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────
# Stage 1: builder — install Python deps with Playwright pre-baked
# ─────────────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install Python dependencies first for layer caching
COPY pyproject.toml requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ─────────────────────────────────────────────────────────────────────
# Stage 2: runtime — slim image with only what we need
# ─────────────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BROWSER_HEADLESS=true \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    OUTPUT_DIR=/app/outputs \
    LOG_LEVEL=INFO

# Create a non-root user for safety
RUN useradd -m -u 1000 -s /bin/bash websearchai

WORKDIR /app

# Copy Python site-packages from builder
COPY --from=builder /usr/lib/python3/dist-packages /usr/lib/python3/dist-packages
COPY --from=builder /usr/local/lib/python3.10/dist-packages /usr/local/lib/python3.10/dist-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY --chown=websearchai:websearchai src ./src
COPY --chown=websearchai:websearchai web ./web
COPY --chown=websearchai:websearchai serve.py run.py pyproject.toml ./

RUN mkdir -p /app/outputs && chown -R websearchai:websearchai /app

USER websearchai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["python", "serve.py"]
