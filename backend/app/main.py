"""
TestQ Backend — FastAPI Application Entry Point.

Initializes the database, registers API routes, and configures
logging and middleware.
"""

import logging
import asyncio
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api.projects import router as projects_router
from app.api.test_runs import router as test_runs_router
from app.api.discovery import router as discovery_router
from app.api.test_cases import router as test_cases_router


def setup_logging():
    """Configure structured logging."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("git").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    setup_logging()
    logger = logging.getLogger("testq")
    logger.info("TestQ Backend starting...")
    logger.info(f"AI Provider: {settings.ai_provider}")
    logger.info(f"Database: {settings.database_url}")

    # Initialize database tables
    await init_db()
    from app.worker.recovery import recover_interrupted_runs
    await recover_interrupted_runs()
    logger.info("Database initialized")

    try:
        yield
    finally:
        from app.worker.control import controls
        active = list(controls.values())
        for control in active:
            control.cancel()
        if active:
            await asyncio.gather(*(control.done.wait() for control in active))
        logger.info("TestQ Backend shutting down")


app = FastAPI(
    title="TestQ",
    description="Independent AI QA Agent — Let AI build it. Let independent AI try to break it.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend in development on any local port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        f"http://localhost:{settings.frontend_port}",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(projects_router)
app.include_router(test_runs_router)
app.include_router(discovery_router)
app.include_router(test_cases_router)


@app.get("/health")
async def health_check():
    """Backend health check endpoint."""
    return {
        "status": "healthy",
        "service": "testq-backend",
        "version": "0.1.0",
        "ai_model": settings.ai_model,
        "ai_provider": settings.ai_provider,
        "ai_enabled": settings.ai_enabled,
    }


@app.get("/api/system/status")
async def system_status():
    """System status and AI preflight verification endpoint."""
    from app.ai import get_ai_provider
    import docker

    ai_info = {
        "status": "DISABLED" if not settings.ai_enabled else "CHECKING",
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "ready": False,
        "message": "AI is disabled" if not settings.ai_enabled else "",
    }
    if settings.ai_enabled:
        try:
            prov = get_ai_provider()
            res = await prov.preflight()
            ai_info.update(res)
        except Exception as e:
            ai_info["status"] = "ERROR"
            ai_info["message"] = str(e)

    docker_ok = False
    try:
        client = docker.from_env()
        docker_ok = client.ping()
    except Exception:
        docker_ok = False

    return {
        "status": "healthy",
        "service": "testq-backend",
        "version": "0.1.0",
        "docker_available": docker_ok,
        "ai": ai_info,
    }


DASHBOARD_FILE = Path(__file__).parent / "static" / "dashboard.html"



@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Interactive TestQ QA dashboard."""
    if DASHBOARD_FILE.exists():
        return HTMLResponse(content=DASHBOARD_FILE.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard file not found</h1>", status_code=404)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "TestQ",
        "tagline": "Independent AI QA Agent",
        "motto": "Let AI build it. Let independent AI try to break it.",
        "version": "0.1.0",
        "docs": "/docs",
        "dashboard": "/dashboard",
    }

