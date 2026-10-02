from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import create_all
from app.routers import analyses, clusters, dockets, documents, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_all()
    yield


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error = detail
    else:
        error = {"code": str(exc.status_code), "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": error})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="EchoTrace", lifespan=lifespan)

    origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(dockets.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(analyses.router, prefix="/api/v1")
    app.include_router(clusters.router, prefix="/api/v1")

    return app


app = create_app()
