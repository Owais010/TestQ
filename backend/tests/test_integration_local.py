"""
Local integration test — tests the pipeline with a local fixture app.

Creates a minimal Express.js app in a temp directory, then tests:
1. Project detection (should detect Node.js)
2. Sandbox creation
3. Dependency installation
4. Application startup
5. Health check

This avoids relying on external GitHub repos for CI-stable testing.
"""

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.project_detector import detect_project
from app.services.sandbox_manager import SandboxManager
from app.services.build_manager import BuildManager
from app.services.health_checker import HealthChecker
from app.schemas.common import SandboxConfig
from app.worker.control import RunControl

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("test.integration")


def create_fixture_app(path: Path) -> Path:
    """Create a minimal Express app for testing."""
    path.mkdir(parents=True, exist_ok=True)

    # package.json
    (path / "package.json").write_text(json.dumps({
        "name": "testq-fixture-app",
        "version": "1.0.0",
        "scripts": {
            "start": "node server.js"
        },
        "dependencies": {
            "express": "^4.18.0"
        }
    }, indent=2))

    # server.js — minimal Express server
    (path / "server.js").write_text("""
const express = require('express');
const app = express();
const port = process.env.PORT || 3000;

app.get('/', (req, res) => {
    res.json({ status: 'ok', app: 'testq-fixture' });
});

app.get('/health', (req, res) => {
    res.json({ healthy: true });
});

app.listen(port, '0.0.0.0', () => {
    console.log('Server running on port ' + port);
});
""")

    # package-lock.json placeholder (triggers npm ci)
    # We'll use npm install instead since we don't have a real lockfile
    return path


async def run_test():
    """Run the full local integration test."""
    fixture_path = Path(tempfile.mkdtemp(prefix="testq_fixture_"))
    container_id = None
    sandbox = None
    control = RunControl(300)

    try:
        # 1. Create fixture app
        logger.info("=== Step 1: Creating fixture app ===")
        create_fixture_app(fixture_path)
        logger.info(f"Fixture app created at: {fixture_path}")

        # 2. Detect project
        logger.info("=== Step 2: Detecting project ===")
        config = detect_project(fixture_path)
        logger.info(f"Framework: {config.framework}")
        logger.info(f"Language: {config.language}")
        logger.info(f"PM: {config.package_manager}")
        logger.info(f"Install: {config.install_command}")
        logger.info(f"Start: {config.start_command}")
        logger.info(f"Port: {config.expected_port}")
        assert config.framework == "nodejs", f"Expected nodejs, got {config.framework}"

        # 3. Create sandbox
        logger.info("=== Step 3: Creating sandbox ===")
        sandbox = SandboxManager(control)
        sandbox_config = SandboxConfig(
            image="testq-sandbox-node:latest",
            cpu_limit=2.0,
            memory_limit="2g",
            timeout=300,
            port_mappings={config.expected_port: 0},
        )
        sandbox_info = sandbox.create(sandbox_config, repo_path=fixture_path)
        container_id = sandbox_info["container_id"]
        host_port = sandbox_info["assigned_ports"].get(config.expected_port)
        logger.info(f"Container: {sandbox_info['short_id']}")
        logger.info(f"Host port: {host_port}")
        assert container_id, "Container was not created"
        assert host_port, "Port was not mapped"

        # 4. Install dependencies
        logger.info("=== Step 4: Installing dependencies ===")
        build_mgr = BuildManager(sandbox)
        install_result = build_mgr.install_dependencies(container_id, config)
        logger.info(f"Install exit_code: {install_result.exit_code}")
        logger.info(f"Install duration: {install_result.duration_seconds}s")
        assert install_result.exit_code == 0, (
            f"Install failed: {install_result.stderr[:300]}"
        )

        # 5. Build (should be None for plain Node.js)
        logger.info("=== Step 5: Building ===")
        build_result = build_mgr.build_project(container_id, config)
        if build_result:
            logger.info(f"Build exit_code: {build_result.exit_code}")
        else:
            logger.info("No build step (expected for Express)")

        # 6. Start application
        logger.info("=== Step 6: Starting application ===")
        sandbox.restrict_network(container_id)
        exec_id = build_mgr.start_application(container_id, config)
        await asyncio.sleep(3)  # Give app time to start

        # 7. Health check
        logger.info("=== Step 7: Health checking ===")
        checker = HealthChecker(max_retries=15, retry_interval=2.0)
        url = f"http://localhost:{host_port}"
        health = await checker.check_sandbox(sandbox, container_id, config.expected_port,
                                              control, asyncio.to_thread, exec_id=exec_id)
        logger.info(f"Healthy: {health.is_healthy}")
        logger.info(f"Status code: {health.status_code}")
        logger.info(f"Response time: {health.response_time_ms}ms")
        logger.info(f"Attempts: {health.attempts}")

        if health.is_healthy:
            logger.info("")
            logger.info("=" * 50)
            logger.info("  INTEGRATION TEST PASSED!")
            logger.info("  Full pipeline: detect -> sandbox -> install")
            logger.info("                 -> build -> start -> health ✓")
            logger.info("=" * 50)
        else:
            logger.error(f"Health check failed: {health.error}")
            # Get container logs
            logs = sandbox.stream_logs(container_id, tail=30)
            logger.error(f"Container logs:\n{logs}")
            logger.error("INTEGRATION TEST FAILED!")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Cleanup
        if sandbox:
            sandbox.cleanup()
            logger.info("Sandbox cleaned up")
        import shutil
        shutil.rmtree(fixture_path, ignore_errors=True)
        logger.info("Fixture cleaned up")


if __name__ == "__main__":
    asyncio.run(run_test())
