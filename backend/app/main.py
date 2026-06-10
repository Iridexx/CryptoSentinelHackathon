"""FastAPI application entrypoint."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.agent.heartbeat import heartbeat
from backend.app.api.routes import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.security.headers import add_security_headers

settings = get_settings()
configure_logging(settings)
logger = get_logger("api")


async def _heartbeat_loop(settings: Settings) -> None:
    """Keep an internal heartbeat active for health checks."""

    while True:
        heartbeat.beat("internal_tick")
        await asyncio.sleep(settings.heartbeat_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop backend runtime tasks."""

    heartbeat.beat("startup")
    task = asyncio.create_task(_heartbeat_loop(settings))
    logger.info(
        "backend_started",
        environment=settings.app_env,
        execution_mode=settings.execution_mode,
        markets_enabled=settings.markets_enabled,
        auth_configured=settings.auth_configured,
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("heartbeat_loop_stopped")
        logger.info("backend_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="CryptoSentinel autonomous trading agent backend foundations.",
        lifespan=lifespan,
    )

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Token"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next: Any) -> Response:
        return await add_security_headers(request, call_next, settings)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next: Any) -> Response:
        started = perf_counter()
        response = await call_next(request)
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        return response

    app.include_router(api_router)
    return app


app = create_app()
