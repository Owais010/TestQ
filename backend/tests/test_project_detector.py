"""
Tests for Project Detector.

Verifies detection of:
- Next.js projects
- React/Vite projects
- Node.js projects
- FastAPI projects
- Unsupported projects (Java, Rust, Go, etc.)
- Malformed/empty projects
- Different package managers (npm, yarn, pnpm)
"""

import pytest
from pathlib import Path

from app.services.project_detector import (
    detect_project,
    UnsupportedProjectError,
    DetectionError,
)

from tests.conftest import (
    create_nextjs_project,
    create_vite_react_project,
    create_nodejs_project,
    create_fastapi_project,
    create_java_project,
    create_empty_project,
    create_yarn_nextjs_project,
    create_pnpm_vite_project,
)


class TestNextjsDetection:
    """Test Next.js project detection."""

    def test_detect_nextjs_with_config(self, tmp_path):
        project = create_nextjs_project(tmp_path / "nextjs")
        config = detect_project(project)

        assert config.framework == "nextjs"
        assert config.language == "typescript"  # has tsconfig.json
        assert config.package_manager == "npm"
        assert "npm ci" in config.install_command
        assert "build" in config.build_command
        assert "start" in config.start_command
        assert config.expected_port == 3000

    def test_detect_nextjs_javascript(self, tmp_path):
        """Next.js without tsconfig should detect as javascript."""
        project = create_nextjs_project(tmp_path / "nextjs-js")
        (project / "tsconfig.json").unlink()  # Remove tsconfig

        config = detect_project(project)
        assert config.framework == "nextjs"
        assert config.language == "javascript"

    def test_detect_nextjs_with_yarn(self, tmp_path):
        project = create_yarn_nextjs_project(tmp_path / "yarn-nextjs")
        config = detect_project(project)

        assert config.framework == "nextjs"
        assert config.package_manager == "yarn"
        assert "yarn" in config.install_command


class TestViteReactDetection:
    """Test React + Vite project detection."""

    def test_detect_vite_react(self, tmp_path):
        project = create_vite_react_project(tmp_path / "vite")
        config = detect_project(project)

        assert config.framework == "vite-react"
        assert config.package_manager == "npm"
        assert "install" in config.install_command
        assert config.build_command is not None
        assert config.expected_port == 4173  # Vite preview default

    def test_detect_pnpm_vite(self, tmp_path):
        project = create_pnpm_vite_project(tmp_path / "pnpm-vite")
        config = detect_project(project)

        assert config.framework == "vite-react"
        assert config.package_manager == "pnpm"
        assert "pnpm" in config.install_command


class TestNodejsDetection:
    """Test generic Node.js project detection."""

    def test_detect_nodejs(self, tmp_path):
        project = create_nodejs_project(tmp_path / "node")
        config = detect_project(project)

        assert config.framework == "nodejs"
        assert config.package_manager == "npm"
        assert "start" in config.start_command

    def test_detect_nodejs_no_build(self, tmp_path):
        """Node.js project without build script should have no build command."""
        project = create_nodejs_project(tmp_path / "node-nobuild")
        config = detect_project(project)

        assert config.build_command is None


class TestFastapiDetection:
    """Test FastAPI project detection."""

    def test_detect_fastapi(self, tmp_path):
        project = create_fastapi_project(tmp_path / "fastapi")
        config = detect_project(project)

        assert config.framework == "fastapi"
        assert config.language == "python"
        assert config.package_manager == "pip"
        assert "requirements.txt" in config.install_command
        assert "uvicorn" in config.start_command
        assert config.expected_port == 8000

    def test_detect_fastapi_main_module(self, tmp_path):
        """Should detect the correct main module path."""
        project = create_fastapi_project(tmp_path / "fastapi-mod")
        config = detect_project(project)

        assert "app.main:app" in config.start_command


class TestUnsupportedProjects:
    """Test detection of unsupported technologies."""

    def test_reject_java(self, tmp_path):
        project = create_java_project(tmp_path / "java")

        with pytest.raises(UnsupportedProjectError) as exc_info:
            detect_project(project)

        assert "Java" in str(exc_info.value)
        assert "Maven" in str(exc_info.value)

    def test_reject_rust(self, tmp_path):
        project = tmp_path / "rust"
        project.mkdir()
        (project / "Cargo.toml").write_text('[package]\nname = "test"')

        with pytest.raises(UnsupportedProjectError) as exc_info:
            detect_project(project)

        assert "Rust" in str(exc_info.value)

    def test_reject_go(self, tmp_path):
        project = tmp_path / "go"
        project.mkdir()
        (project / "go.mod").write_text("module test")

        with pytest.raises(UnsupportedProjectError) as exc_info:
            detect_project(project)

        assert "Go" in str(exc_info.value)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_project(self, tmp_path):
        project = create_empty_project(tmp_path / "empty")

        with pytest.raises(DetectionError):
            detect_project(project)

    def test_nonexistent_path(self):
        with pytest.raises(DetectionError):
            detect_project("/nonexistent/path/foo")

    def test_malformed_package_json(self, tmp_path):
        project = tmp_path / "malformed"
        project.mkdir()
        (project / "package.json").write_text("this is not json {{{")

        with pytest.raises(DetectionError):
            detect_project(project)

    def test_package_json_without_scripts(self, tmp_path):
        """package.json with no scripts and no framework deps."""
        import json
        project = tmp_path / "no-scripts"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({
            "name": "empty-pkg",
            "version": "1.0.0",
            "dependencies": {"lodash": "4.0.0"},
        }))

        with pytest.raises(DetectionError):
            detect_project(project)

    def test_detected_files_populated(self, tmp_path):
        """Config should list the files that informed detection."""
        project = create_nextjs_project(tmp_path / "files-check")
        config = detect_project(project)

        assert "package.json" in config.detected_files
        assert len(config.detected_files) > 1
