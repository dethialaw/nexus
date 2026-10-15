"""FastAPI application."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from nexus.bootstrap import Container, build_container
from nexus.entrypoints.api.schemas import Health
from nexus.settings import ApiSettings

logger = logging.getLogger("nexus.api")


def create_app(
    container_factory: Callable[[], Container] = build_container,
    api_settings: ApiSettings | None = None,
) -> FastAPI:
    api_settings = api_settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container_factory()
        try:
            yield
        finally:
            await app.state.container.dispose()

    app = FastAPI(title="Nexus", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.get(
        "/health",
        operation_id="getHealth",
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Health}},
    )
    async def health(request: Request, response: Response) -> Health:
        container: Container = request.app.state.container
        try:
            await container.check_database()
        except Exception:
            logger.exception("database health check failed")
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return Health(status="unavailable", database="unavailable")
        return Health(status="ok", database="ok")

    return app
