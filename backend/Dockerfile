# One image, two commands: the API by default, `nexus-batch` by overriding the command.

FROM ghcr.io/astral-sh/uv:0.13.6-python3.14-trixie-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY AGENTS.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-trixie AS runtime
RUN useradd --system --uid 10001 --no-create-home nexus
WORKDIR /app
COPY --from=build --chown=nexus:nexus /app/.venv /app/.venv
COPY --from=build --chown=nexus:nexus /app/alembic.ini /app/alembic.ini
COPY --from=build --chown=nexus:nexus /app/alembic /app/alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000
USER nexus
EXPOSE 8000
CMD ["nexus-api"]
