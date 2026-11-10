"""Application entrypoint and app factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.middleware import TRACE_ID_HEADER, TraceMiddleware
from app.api.v1.router import api_router
from app.composition import (
    close_clients,
    get_agent_memory_client,
    get_promotion_service,
    get_tagger_service,
)
from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    tagger: asyncio.Task[None] | None = None
    if settings.TAGGER_ENABLED and get_agent_memory_client() is not None:
        interval = settings.TAGGER_INTERVAL_HOURS * 3600
        tagger = asyncio.create_task(get_tagger_service().loop(interval))
    promotion: asyncio.Task[None] | None = None
    if settings.PROMOTION_ENABLED and get_agent_memory_client() is not None:
        every = settings.PROMOTION_JOB_EVERY_MINUTES * 60
        promotion = asyncio.create_task(get_promotion_service().loop(every))
    try:
        yield
    finally:
        if promotion is not None:
            promotion.cancel()
            with suppress(asyncio.CancelledError):
                await promotion
        if tagger is not None:
            tagger.cancel()
            with suppress(asyncio.CancelledError):
                await tagger
        await close_clients()


def create_app() -> FastAPI:
    setup_logging()
    secret = settings.SESSION_SECRET_KEY.get_secret_value()
    if settings.ENVIRONMENT != "development" and secret in ("", "dev-insecure-change-me"):
        raise RuntimeError("SESSION_SECRET_KEY must be set to a strong secret outside development")
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        lifespan=lifespan,
    )
    # Added innermost first: Trace runs inside Session (so it can log the user),
    # and both run inside CORS, so errors still carry CORS headers.
    app.add_middleware(TraceMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        same_site="lax",
        https_only=settings.ENVIRONMENT != "development",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[TRACE_ID_HEADER],
    )
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
