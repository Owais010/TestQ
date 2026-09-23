"""
Tests for the FastAPI application and API endpoints.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def test_db():
    """Create a fresh test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Test the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "testq-backend"

    @pytest.mark.asyncio
    async def test_root(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TestQ"


class TestProjectsAPI:
    """Test project API endpoints."""

    @pytest.mark.asyncio
    async def test_create_project(self, client):
        response = await client.post(
            "/api/projects",
            json={
                "repository_url": "https://github.com/test/repo",
                "branch": "main",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["repository_url"] == "https://github.com/test/repo"
        assert data["default_branch"] == "main"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_project_invalid_url(self, client):
        response = await client.post(
            "/api/projects",
            json={"repository_url": "not-a-url", "branch": "main"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_project_deduplication(self, client):
        """Creating the same project twice should return the existing one."""
        resp1 = await client.post(
            "/api/projects",
            json={"repository_url": "https://github.com/test/dedup", "branch": "main"},
        )
        resp2 = await client.post(
            "/api/projects",
            json={"repository_url": "https://github.com/test/dedup", "branch": "main"},
        )
        assert resp1.json()["id"] == resp2.json()["id"]

    @pytest.mark.asyncio
    async def test_get_project(self, client):
        # Create first
        create_resp = await client.post(
            "/api/projects",
            json={"repository_url": "https://github.com/test/getme", "branch": "main"},
        )
        project_id = create_resp.json()["id"]

        # Get it back
        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == project_id

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client):
        response = await client.get("/api/projects/nonexistent-id")
        assert response.status_code == 404


class TestTestRunsAPI:
    """Test test-run API endpoints."""

    @pytest.mark.asyncio
    async def test_create_test_run(self, client):
        response = await client.post(
            "/api/test-runs",
            json={
                "repository_url": "https://github.com/test/run-test",
                "branch": "main",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "QUEUED"
        assert "id" in data
        assert data["branch"] == "main"
        assert data["progress"] is not None

    @pytest.mark.asyncio
    async def test_create_test_run_invalid_url(self, client):
        response = await client.post(
            "/api/test-runs",
            json={"repository_url": "invalid", "branch": "main"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_test_run(self, client):
        # Create first
        create_resp = await client.post(
            "/api/test-runs",
            json={"repository_url": "https://github.com/test/get-run", "branch": "main"},
        )
        run_id = create_resp.json()["id"]

        # Get it back
        get_resp = await client.get(f"/api/test-runs/{run_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == run_id

    @pytest.mark.asyncio
    async def test_get_test_run_not_found(self, client):
        response = await client.get("/api/test-runs/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_test_run_logs(self, client):
        create_resp = await client.post(
            "/api/test-runs",
            json={"repository_url": "https://github.com/test/logs-run", "branch": "main"},
        )
        run_id = create_resp.json()["id"]

        logs_resp = await client.get(f"/api/test-runs/{run_id}/logs")
        assert logs_resp.status_code == 200
        assert "logs" in logs_resp.json()
