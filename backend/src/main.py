from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.api import (
    agent,
    analytics,
    auth,
    batch_tasks,
    chats,
    detections,
    devices,
    files,
    openapi,
    records,
    thresholds,
)
from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, create_all
from src.core.exceptions import register_exception_handlers
from src.core.logging import RequestLoggingMiddleware, configure_logging
from src.core.responses import ok
from src.repositories.store import mark_stale_processing_failed
from src.services.bootstrap import ensure_seed_data

_settings = get_settings()
configure_logging(_settings)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.auto_create_tables:
        await create_all()
        async with AsyncSessionLocal() as db:
            await ensure_seed_data(db)
            await mark_stale_processing_failed(db)
            await db.commit()
    yield
    # Cleanly close connection pool on shutdown
    from src.integrations import get_cgm_client

    try:
        client = get_cgm_client()
        if hasattr(client, "close"):
            await client.close()
    except Exception:
        pass


app = FastAPI(
    title="Overseas CGM Agent Backend MVP", version="0.1.0", lifespan=lifespan
)
register_exception_handlers(app)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(chats.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(detections.router, prefix="/api/v1")
app.include_router(batch_tasks.router, prefix="/api/v1")
app.include_router(thresholds.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(openapi.router, prefix="/openapi/v1")


@app.get("/health")
async def health() -> dict:
    return ok({"status": "ok"})


# ALB 默认用 HEAD / 做健康检查，也兼容
@app.head("/")
async def alb_health_head():
    return Response(status_code=200)


@app.get("/")
async def alb_health_get() -> dict:
    return ok({"status": "ok"})
