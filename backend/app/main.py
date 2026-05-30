from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.bootstrap import ensure_runtime_schema
from app.db.session import engine
from app.services.trip_jobs import recover_interrupted_trip_jobs

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    recover_interrupted_trip_jobs()
    if settings.is_sqlite and settings.app_env != "test":
        import json as _json
        print(
            "trip_architect.startup "
            + _json.dumps({
                "level": "WARNING",
                "message": (
                    "SQLite is active. All data (users, trips, bookings) will be lost on "
                    "container restart or Railway redeploy. Set DATABASE_URL to a PostgreSQL "
                    "connection string (e.g. postgresql+psycopg://user:pass@host/db) to persist data."
                ),
            }),
            flush=True,
        )
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_prefix)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        requested = static_dir / full_path
        if requested.is_file():
            return FileResponse(requested)
        return FileResponse(static_dir / "index.html")
