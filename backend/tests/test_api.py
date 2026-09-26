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
async def test_db(monkeypatch):
    """Create a fresh test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # API contract tests do not execute external repositories. Pipeline behavior
    # is exercised separately against this same kind of isolated session factory.
    from unittest.mock import AsyncMock
    from app.api import test_runs
    from app.worker.control import controls
    monkeypatch.setattr(test_runs, "async_session", session_maker)
    monkeypatch.setattr(test_runs, "_run_pipeline", AsyncMock())

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
    controls.clear()
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
        assert "dashboard" in data

    @pytest.mark.asyncio
    async def test_dashboard(self, client):
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "TestQ" in response.text



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

    @pytest.mark.asyncio
    async def test_create_test_run_testing_requires_discovery(self, client):
        """Testing without discovery must be rejected with HTTP 400."""
        response = await client.post(
            "/api/test-runs",
            json={
                "repository_url": "https://github.com/test/no-discovery",
                "discover": False,
                "testing_enabled": True,
            },
        )
        assert response.status_code == 400
        assert "Testing requires discovery to be enabled" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_test_run_testing_enabled_valid(self, client):
        """Valid testing request with discovery enabled must be accepted with HTTP 201."""
        response = await client.post(
            "/api/test-runs",
            json={
                "repository_url": "https://github.com/test/valid-testing",
                "discover": True,
                "testing_enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["testing_enabled"] is True
        assert data["discovery_enabled"] is True

    @pytest.mark.asyncio
    async def test_list_test_runs(self, client):
        """GET /api/test-runs?limit=1 must return 200 with runs and total."""
        # Create two test runs
        await client.post(
            "/api/test-runs",
            json={"repository_url": "https://github.com/test/list-run-1", "branch": "main"},
        )
        await client.post(
            "/api/test-runs",
            json={"repository_url": "https://github.com/test/list-run-2", "branch": "main"},
        )

        # Query with limit=1
        resp = await client.get("/api/test-runs?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data
        assert len(data["runs"]) == 1
        assert data["total"] >= 2

        # Query without limit (default limit=10)
        resp_all = await client.get("/api/test-runs")
        assert resp_all.status_code == 200
        data_all = resp_all.json()
        assert len(data_all["runs"]) >= 2
        # Check ordering: newest first
        assert data_all["runs"][0]["created_at"] >= data_all["runs"][1]["created_at"]

