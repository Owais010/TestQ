"""
Health Checker.

Performs real HTTP health checks against the application
running inside the sandbox. Uses retries with backoff since
applications need startup time.
"""

import asyncio
import logging
import time

import httpx

from app.schemas.common import HealthCheckResult

logger = logging.getLogger("testq.health")


class HealthChecker:
    """Check if an application is reachable and responding."""

    def __init__(
        self,
        max_retries: int = 30,
        retry_interval: float = 2.0,
        timeout: float = 5.0,
    ):
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.timeout = timeout

    async def check(self, url: str) -> HealthCheckResult:
        """
        Perform health check with retries.

        Tries to GET the URL up to max_retries times with
        retry_interval between attempts.

        Args:
            url: The URL to check (e.g., http://localhost:32768)

        Returns:
            HealthCheckResult with status.
        """
        logger.info(f"Health checking: {url} (max {self.max_retries} attempts)")

        last_error = None

        for attempt in range(1, self.max_retries + 1):
            start = time.monotonic()
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url)
                    elapsed = (time.monotonic() - start) * 1000

                    # Accept any 2xx or 3xx response as "healthy"
                    # Also accept 401/403 (auth-protected but responding)
                    if response.status_code < 500:
                        logger.info(
                            f"Health check passed: {url} "
                            f"(status={response.status_code}, "
                            f"attempt={attempt}, "
                            f"time={elapsed:.0f}ms)"
                        )
                        return HealthCheckResult(
                            is_healthy=True,
                            url=url,
                            status_code=response.status_code,
                            response_time_ms=round(elapsed, 2),
                            attempts=attempt,
                        )
                    else:
                        last_error = (
                            f"HTTP {response.status_code} on attempt {attempt}"
                        )
                        logger.debug(
                            f"Health check attempt {attempt}: {last_error}"
                        )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = f"Connection failed on attempt {attempt}: {type(e).__name__}"
                logger.debug(last_error)
            except Exception as e:
                last_error = f"Unexpected error on attempt {attempt}: {e}"
                logger.debug(last_error)

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_interval)

        logger.warning(f"Health check failed after {self.max_retries} attempts: {url}")

        return HealthCheckResult(
            is_healthy=False,
            url=url,
            error=last_error or "Max retries exceeded",
            attempts=self.max_retries,
        )

    async def check_sandbox(self, sandbox, container_id, port, control, blocking, exec_id=None):
        """Probe loopback inside a network-disconnected container; no redirects."""
        url = f"http://127.0.0.1:{port}"
        error = "Application did not respond"
        attempts_log: list[str] = []
        for attempt in range(1, self.max_retries + 1):
            control.check()
            if exec_id:
                state = await blocking(sandbox.client.api.exec_inspect, exec_id)
                if not state["Running"]:
                    error = f"Application exited with code {state['ExitCode']}"
                    break
            result = await blocking(
                sandbox.execute, container_id,
                f"curl --noproxy '*' --max-time {self.timeout} -s -o /dev/null -w '%{{http_code}}' {url}",
                timeout=self.timeout + 2, source="_health_probe",
            )
            code = int(result.stdout) if result.stdout.isdigit() else 0
            if result.exit_code == 0 and (200 <= code < 400 or code in (401, 403)):
                attempts_log.append(f"Attempt {attempt}: HTTP {code}")
                return HealthCheckResult(
                    is_healthy=True, url=url, status_code=code, attempts=attempt,
                    details="; ".join(attempts_log),
                )
            if code == 0:
                attempts_log.append(f"Attempt {attempt}: connection pending")
            else:
                attempts_log.append(f"Attempt {attempt}: HTTP {code}")
            error = f"HTTP {code}: {result.stderr}"
            until = time.monotonic() + self.retry_interval
            while time.monotonic() < until:
                control.check()
                await asyncio.sleep(0.1)
        return HealthCheckResult(
            is_healthy=False, url=url, error=error, attempts=attempt,
            details="; ".join(attempts_log),
        )
