"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8000

    * /docs            - interactive API docs (Swagger UI)
    * /health          - liveness + component health
    * /api/v1/...      - all business endpoints
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1 import api_router
from app.config import settings
from app.core.logger import get_logger, setup_logging
from app.db.postgres import check_db_connection, init_db, seed_default_data
from app.db.vector_db import get_vector_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: logging, schema, seed data. (DB outages are logged, not fatal.)"""
    setup_logging()
    logger = get_logger("mira.main")
    logger.info("Starting %s v%s (%s)", settings.APP_NAME, settings.VERSION, settings.ENVIRONMENT)

    try:
        init_db()
    except Exception as exc:
        logger.error("init_db failed (is PostgreSQL running?): %s", exc)
    try:
        seed_default_data()
    except Exception as exc:
        logger.error("seed_default_data failed: %s", exc)

    # Warm the vector store connection in the background of startup.
    try:
        get_vector_store().ensure_connected()
    except Exception as exc:
        logger.warning("Vector store warm-up failed: %s", exc)

    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.BASE_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------- #
# Middleware / error handling
# ---------------------------------------------------------------------- #


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Request timing + logging (skip noise paths)."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if not request.url.path.startswith(("/docs", "/openapi", "/redoc")):
        get_logger("mira.http").info(
            "%s %s -> %d (%.0f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    get_logger("mira.errors").exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------- #
# Routes
# ---------------------------------------------------------------------- #
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
def health():
    """Liveness + component health (used by Docker HEALTHCHECK & demos)."""
    db_ok = check_db_connection()
    vector = get_vector_store().health()
    embedding_backend = None
    try:
        from app.services.matching_engine.qwen_embedding import get_embedding_service

        embedding_backend = get_embedding_service().backend
    except Exception:
        embedding_backend = "unavailable"

    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "components": {
            "postgres": "up" if db_ok else "down",
            "vector_store": vector,
            "embedding_backend": embedding_backend,
        },
    }


@app.get("/", tags=["meta"])
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "api": settings.API_V1_PREFIX,
    }

