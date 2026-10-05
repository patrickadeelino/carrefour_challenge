FROM ghcr.io/astral-sh/uv:0.12.20 AS uv
FROM python:3.11-slim AS base

COPY --from=uv /uv /uvx /bin/

WORKDIR /workspace/apps/ocr_mcp
RUN useradd --create-home --uid 10001 --user-group app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
# Compose supplies the shared package from its monorepo-relative path.
COPY --from=observability . /workspace/packages/carrefour_observability/
COPY pyproject.toml uv.lock README.md ./

FROM base AS runtime-deps
RUN uv sync --frozen --no-dev --no-install-project

FROM runtime-deps AS dev-deps
RUN uv sync --frozen --group dev --no-install-project

FROM runtime-deps AS runtime
COPY --chown=app:app src ./src
RUN uv sync --frozen --no-dev && chown -R app:app /app /workspace/apps/ocr_mcp

ENV CARREFOUR_IMAGE_STORAGE_PATH=/var/run/carrefour/images
ENV CARREFOUR_OCR_ALLOWED_HOSTS=ocr-mcp:8000
ENV PATH=/app/.venv/bin:$PATH

USER app
CMD ["python", "-m", "carrefour_ocr_mcp"]

FROM dev-deps AS dev
COPY --chown=app:app src ./src
RUN uv sync --frozen --group dev && chown -R app:app /app /workspace/apps/ocr_mcp
COPY --chown=app:app tests ./tests

ENV CARREFOUR_IMAGE_STORAGE_PATH=/var/run/carrefour/images
ENV CARREFOUR_OCR_ALLOWED_HOSTS=ocr-mcp:8000
ENV PATH=/app/.venv/bin:$PATH

USER app
CMD ["python", "-m", "carrefour_ocr_mcp"]
