"""
Tests for Pydantic schemas.

Verify validation, required fields, defaults, and serialization.
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import ProjectConfig, ExecutionResult, SandboxConfig, HealthCheckResult
from app.schemas.project import ProjectCreate, ProjectResponse
from app.schemas.test_run import TestRunCreate, TestRunResponse, TestRunProgress


class TestProjectConfig:
    """Test ProjectConfig schema."""

    def test_valid_config(self):
        config = ProjectConfig(
            language="typescript",
            framework="nextjs",
            package_manager="npm",
            install_command="npm ci",
            build_command="npm run build",
            start_command="npm run start",
            expected_port=3000,
        )
        assert config.framework == "nextjs"
        assert config.expected_port == 3000

    def test_optional_build_command(self):
        config = ProjectConfig(
            language="python",
            framework="fastapi",
            package_manager="pip",
            install_command="pip install -r requirements.txt",
            start_command="uvicorn app.main:app",
        )
        assert config.build_command is None

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ProjectConfig(
                language="typescript",
                # Missing framework, package_manager, etc.
            )

    def test_serialization(self):
        config = ProjectConfig(
            language="typescript",
            framework="nextjs",
            package_manager="npm",
            install_command="npm ci",
            start_command="npm start",
        )
        data = config.model_dump()
        assert isinstance(data, dict)
        assert data["framework"] == "nextjs"


class TestExecutionResult:
    """Test ExecutionResult schema."""

    def test_successful_result(self):
        result = ExecutionResult(
            command="npm ci",
            exit_code=0,
            stdout="added 100 packages",
            stderr="",
        )
        assert result.exit_code == 0
        assert result.timed_out is False

    def test_failed_result(self):
        result = ExecutionResult(
            command="npm run build",
            exit_code=1,
            stderr="Error: Module not found",
        )
        assert result.exit_code == 1

    def test_timeout_result(self):
        result = ExecutionResult(
            command="npm run build",
            exit_code=-1,
            timed_out=True,
        )
        assert result.timed_out is True


class TestProjectCreate:
    """Test ProjectCreate request schema."""

    def test_valid_request(self):
        req = ProjectCreate(
            repository_url="https://github.com/user/project",
            branch="main",
        )
        assert req.repository_url == "https://github.com/user/project"
        assert req.branch == "main"

    def test_default_branch(self):
        req = ProjectCreate(repository_url="https://github.com/user/project")
        assert req.branch is None  # remote default branch, resolved during clone

    def test_missing_url(self):
        with pytest.raises(ValidationError):
            ProjectCreate()


class TestTestRunCreate:
    """Test TestRunCreate request schema."""

    def test_valid_request(self):
        req = TestRunCreate(
            repository_url="https://github.com/user/project",
            branch="develop",
        )
        assert req.branch == "develop"

    def test_missing_url(self):
        with pytest.raises(ValidationError):
            TestRunCreate()


class TestTestRunProgress:
    """Test TestRunProgress schema."""

    def test_default_progress(self):
        progress = TestRunProgress()
        assert progress.cloning == "pending"
        assert progress.building == "pending"
        assert progress.report == "pending"

    def test_custom_progress(self):
        progress = TestRunProgress(
            cloning="completed",
            analyzing="completed",
            building="in_progress",
        )
        assert progress.cloning == "completed"
        assert progress.building == "in_progress"
        assert progress.starting == "pending"  # Still default


class TestHealthCheckResult:
    """Test HealthCheckResult schema."""

    def test_healthy(self):
        result = HealthCheckResult(
            is_healthy=True,
            url="http://localhost:3000",
            status_code=200,
            response_time_ms=42.5,
            attempts=1,
        )
        assert result.is_healthy
        assert result.status_code == 200

    def test_unhealthy(self):
        result = HealthCheckResult(
            is_healthy=False,
            url="http://localhost:3000",
            error="Connection refused",
            attempts=30,
        )
        assert not result.is_healthy
        assert result.status_code is None


class TestSandboxConfig:
    """Test SandboxConfig schema."""

    def test_defaults(self):
        config = SandboxConfig(image="testq-sandbox-node:latest")
        assert config.cpu_limit == 2.0
        assert config.memory_limit == "2g"
        assert config.timeout == 600
        assert config.working_dir == "/workspace"

    def test_custom_config(self):
        config = SandboxConfig(
            image="testq-sandbox-python:latest",
            cpu_limit=1.0,
            memory_limit="1g",
            timeout=300,
            port_mappings={8000: 0},
        )
        assert config.cpu_limit == 1.0
        assert config.port_mappings == {8000: 0}
