"""
TestQ Backend — FastAPI Application Entry Point.

Initializes the database, registers API routes, and configures
logging and middleware.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api.projects import router as projects_router
from app.api.test_runs import router as test_runs_router


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
    logger.info("Database initialized")

    yield

    logger.info("TestQ Backend shutting down")


app = FastAPI(
    title="TestQ",
    description="Independent AI QA Agent — Let AI build it. Let independent AI try to break it.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        f"http://localhost:{settings.frontend_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(projects_router)
app.include_router(test_runs_router)


@app.get("/health")
async def health_check():
    """Backend health check endpoint."""
    return {
        "status": "healthy",
        "service": "testq-backend",
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "TestQ",
        "tagline": "Independent AI QA Agent",
        "motto": "Let AI build it. Let independent AI try to break it.",
        "version": "0.1.0",
        "docs": "/docs",
    }
