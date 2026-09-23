"""Test configuration and fixtures."""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    """Create a test database session with in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary directory that simulates a cloned repository."""
    return tmp_path


def create_nextjs_project(path: Path) -> Path:
    """Create a minimal Next.js project structure for testing."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({
        "name": "test-nextjs-app",
        "version": "1.0.0",
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
        },
        "dependencies": {
            "next": "14.0.0",
            "react": "18.2.0",
            "react-dom": "18.2.0",
        },
    }))
    (path / "next.config.js").write_text("module.exports = {}")
    (path / "tsconfig.json").write_text("{}")
    (path / "package-lock.json").write_text("{}")
    return path


def create_vite_react_project(path: Path) -> Path:
    """Create a minimal Vite + React project structure for testing."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({
        "name": "test-vite-app",
        "version": "1.0.0",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "react": "18.2.0",
            "react-dom": "18.2.0",
        },
        "devDependencies": {
            "vite": "5.0.0",
            "@vitejs/plugin-react": "4.0.0",
        },
    }))
    (path / "vite.config.js").write_text("export default {}")
    (path / "tsconfig.json").write_text("{}")
    return path


def create_nodejs_project(path: Path) -> Path:
    """Create a minimal Node.js (Express) project structure for testing."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({
        "name": "test-node-app",
        "version": "1.0.0",
        "scripts": {
            "start": "node server.js",
        },
        "dependencies": {
            "express": "4.18.0",
        },
    }))
    (path / "server.js").write_text("const express = require('express');")
    (path / "package-lock.json").write_text("{}")
    return path


def create_fastapi_project(path: Path) -> Path:
    """Create a minimal FastAPI project structure for testing."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    app_dir = path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n"
    )
    return path


def create_java_project(path: Path) -> Path:
    """Create a minimal Java/Maven project (unsupported)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "pom.xml").write_text("<project></project>")
    src_dir = path / "src" / "main" / "java"
    src_dir.mkdir(parents=True)
    return path


def create_empty_project(path: Path) -> Path:
    """Create an empty directory."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_yarn_nextjs_project(path: Path) -> Path:
    """Create a Next.js project using yarn."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({
        "name": "test-yarn-nextjs",
        "scripts": {"build": "next build", "start": "next start"},
        "dependencies": {"next": "14.0.0", "react": "18.2.0", "react-dom": "18.2.0"},
    }))
    (path / "yarn.lock").write_text("")
    return path


def create_pnpm_vite_project(path: Path) -> Path:
    """Create a Vite project using pnpm."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({
        "name": "test-pnpm-vite",
        "scripts": {"build": "vite build", "preview": "vite preview"},
        "dependencies": {"react": "18.2.0", "react-dom": "18.2.0"},
        "devDependencies": {"vite": "5.0.0"},
    }))
    (path / "vite.config.ts").write_text("export default {}")
    (path / "pnpm-lock.yaml").write_text("")
    return path
