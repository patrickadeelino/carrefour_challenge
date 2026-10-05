FROM ghcr.io/astral-sh/uv:0.12.20 AS uv
FROM python:3.11-slim AS base

COPY --from=uv /uv /uvx /bin/

WORKDIR /workspace/apps/schedule_api
RUN useradd --create-home --uid 10001 --user-group app \
    && mkdir -p /var/lib/carrefour/schedule \
    && chown -R app:app /var/lib/carrefour/schedule

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
COPY --from=observability . /workspace/packages/carrefour_observability/
COPY pyproject.toml uv.lock README.md ./

FROM base AS runtime-deps
RUN uv sync --frozen --no-dev --no-install-project

FROM runtime-deps AS dev-deps
RUN uv sync --frozen --group dev --no-install-project

FROM runtime-deps AS runtime
COPY --chown=app:app src ./src
RUN uv sync --frozen --no-dev \
    && chown -R app:app /app /workspace/apps/schedule_api

ENV CARREFOUR_SCHEDULE_DATABASE_PATH=/var/lib/carrefour/schedule/appointments.sqlite3
ENV PATH=/app/.venv/bin:$PATH

USER app
CMD ["python", "-m", "carrefour_schedule_api"]

FROM dev-deps AS dev
COPY --chown=app:app src ./src
RUN uv sync --frozen --group dev \
    && chown -R app:app /app /workspace/apps/schedule_api
COPY --chown=app:app tests ./tests

ENV CARREFOUR_SCHEDULE_DATABASE_PATH=/var/lib/carrefour/schedule/appointments.sqlite3
ENV PATH=/app/.venv/bin:$PATH

USER app
CMD ["python", "-m", "carrefour_schedule_api"]
