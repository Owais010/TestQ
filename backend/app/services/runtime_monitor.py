"""Runtime Monitor (Phase 4.6).
Captures stdout, stderr, HTTP 500/404, browser console errors, page errors, failed requests,
crashes, and timeout events. Stores them as OBSERVATIONS (never assumes every observation is a bug).
Connects relevant observations to test results.
"""
from __future__ import annotations

import time
from typing import Any
from pydantic import BaseModel, Field


class RuntimeObservation(BaseModel):
    """A single captured runtime event or observation."""
    id: str
    kind: str  # "http_error" | "console_error" | "page_error" | "failed_request" | "server_stderr" | "timeout" | "crash"
    source: str  # "browser" | "server" | "network"
    severity: str  # "error" | "warning" | "info"
    message: str
    page_url: str | None = None
    test_id: str | None = None
    timestamp: float = Field(default_factory=time.time)


class RuntimeMonitor:
    """Collects, correlates, and organizes runtime observations during execution."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.observations: list[RuntimeObservation] = []
        self._counter = 1

    def observe(
        self,
        kind: str,
        message: str,
        *,
        source: str = "browser",
        severity: str = "warning",
        page_url: str | None = None,
        test_id: str | None = None,
    ) -> RuntimeObservation:
        """Record a single runtime observation."""
        obs_id = f"OBS-{self._counter:04d}"
        self._counter += 1
        obs = RuntimeObservation(
            id=obs_id,
            kind=kind,
            source=source,
            severity=severity,
            message=str(message)[:2000],
            page_url=page_url,
            test_id=test_id,
        )
        self.observations.append(obs)
        return obs

    def ingest_server_logs(self, log_stream: list[tuple[str, str, str]]):
        """Ingest raw container logs (source, stream, text)."""
        for source, stream, value in log_stream:
            if stream == "stderr" and value.strip():
                for line in value.splitlines()[:50]:
                    if line.strip():
                        self.observe(
                            kind="server_stderr",
                            source="server",
                            severity="warning" if "warn" in line.lower() else "error",
                            message=line.strip(),
                        )

    def ingest_browser_events(self, console_logs: list[dict], network_events: list[dict], page_errors: list[str], test_id: str | None = None):
        """Ingest logs and events recorded during a test or discovery run."""
        for log in console_logs:
            log_type = log.get("type", "log")
            if log_type in ("error", "warning"):
                self.observe(
                    kind="console_error" if log_type == "error" else "console_warning",
                    source="browser",
                    severity="error" if log_type == "error" else "warning",
                    message=log.get("text", "")[:500],
                    test_id=test_id,
                )

        for err in page_errors:
            self.observe(
                kind="page_error",
                source="browser",
                severity="error",
                message=str(err)[:500],
                test_id=test_id,
            )

        for req in network_events:
            url = req.get("url", "")
            failure = str(req.get("failure", ""))
            if req.get("blocked") or "blockedbyclient" in failure.lower() or "blocked" in failure.lower():
                self.observe(
                    kind="EXTERNAL_BLOCKED_BY_SANDBOX",
                    source="network",
                    severity="info",
                    message=f"External request blocked by sandbox security boundary: {url}",
                    test_id=test_id,
                )
            elif req.get("failure"):
                self.observe(
                    kind="failed_request",
                    source="network",
                    severity="warning",
                    message=f"Request to {url} failed: {failure}",
                    test_id=test_id,
                )

    def get_observations_for_test(self, test_id: str) -> list[dict[str, Any]]:
        """Get all observations linked to a specific test."""
        return [o.model_dump() for o in self.observations if o.test_id == test_id]

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Export all observations as a list of dicts."""
        return [o.model_dump() for o in self.observations]
