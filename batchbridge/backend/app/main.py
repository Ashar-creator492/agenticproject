import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api import (
    auth,
    cases,
    catalog,
    escalations,
    evidence,
    health,
    imports,
    inspections,
    reports,
)
from app.config import get_settings
from app.database import SessionLocal
from app.dependencies import enforce_origin
from app.models import AgentRun
from app.seed import seed_demo_data
from app.services.investigation import execute_investigation


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recovery_tasks: list[asyncio.Task] = []
    if get_settings().seed_demo_data:
        with SessionLocal() as db:
            seed_demo_data(db)
    with SessionLocal() as db:
        # Resume work left in-flight by a previous process shutdown.
        interrupted = db.scalars(
            select(AgentRun).where(AgentRun.status.in_(["queued", "running"]))
        ).all()
        for run in interrupted:
            run.status = "queued"
        db.commit()
        recovery_tasks = [asyncio.create_task(execute_investigation(run.id)) for run in interrupted]
    yield
    for task in recovery_tasks:
        if not task.done():
            task.cancel()


app = FastAPI(
    title="Escalera API",
    version="0.1.0",
    description="Human-approved international food batch investigation workflow",
    lifespan=lifespan,
    dependencies=[Depends(enforce_origin)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(evidence.router, prefix="/api/v1")
app.include_router(imports.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(inspections.router, prefix="/api/v1")
app.include_router(escalations.router, prefix="/api/v1")

frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_root():
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_fallback(path: str):
        if path.startswith(("api/", "health/")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (frontend_dist / path).resolve()
        if frontend_dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")

else:

    @app.get("/")
    def root():
        return {
            "name": "Escalera API",
            "docs": "/docs",
            "health": "/health/ready",
        }
