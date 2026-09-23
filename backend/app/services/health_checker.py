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
