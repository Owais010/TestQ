"""Deterministic Bug Deduplication Service (Phase 4.6).
Groups related test failures into unique defects based on normalized signatures.
NO LLM used for deduplication — pure deterministic normalization.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Sequence


def normalize_error_message(message: str | None) -> str:
    """Normalize dynamic values (numbers, UUIDs, hex strings, timestamps) from error strings."""
    if not message:
        return "Unknown error"
    # Replace UUIDs
    msg = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", message, flags=re.I)
    # Replace dynamic order numbers like ORD-12345
    msg = re.sub(r"ORD-\d+", "ORD-<ID>", msg)
    # Replace timestamps
    msg = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "<TIME>", msg)
    # Replace ports and localhost addresses
    msg = re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1:<PORT>", msg)
    msg = re.sub(r"localhost:\d+", "localhost:<PORT>", msg)
    # Collapse multiple whitespace
    msg = re.sub(r"\s+", " ", msg).strip()
    return msg[:300]


def extract_target_route(test_case_def: dict[str, Any] | None) -> str:
    """Extract primary target route or endpoint path from test definition."""
    if not test_case_def:
        return "/"
    t_type = test_case_def.get("type", "ui")
    if t_type == "ui":
        steps = test_case_def.get("steps") or []
        for s in steps:
            if s.get("action") == "goto" and s.get("target"):
                return s.get("target")
        return "/"
    else:
        req = test_case_def.get("request") or {}
        return req.get("path") or "/"


def compute_defect_signature(
    target_route: str,
    failed_assertion: str,
    normalized_error: str,
    http_status: int | None = None,
) -> str:
    """Compute deterministic defect signature."""
    status_part = f"HTTP_{http_status}" if http_status else "NO_STATUS"
    norm_route = target_route.rstrip("/") or "/"
    raw_sig = f"{norm_route}::{failed_assertion}::{status_part}::{normalized_error[:100]}"
    return raw_sig


class DefectDeduplicator:
    """Groups failures into unique defects deterministically."""

    @classmethod
    def deduplicate(
        cls,
        failures: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Group failures by normalized signature into unique defects.
        Returns:
            List of unique defect records with 'seen_in_tests', 'test_count', 'display_badge'.
        """
        groups: dict[str, list[dict[str, Any]]] = {}

        for f in failures:
            target = f.get("target") or extract_target_route(f.get("test_definition"))
            assertion = f.get("failed_assertion") or "assertion_failed"
            error = normalize_error_message(f.get("error") or f.get("summary") or "")
            http_status = f.get("http_status")

            sig = compute_defect_signature(target, assertion, error, http_status)
            if sig not in groups:
                groups[sig] = []
            groups[sig].append(f)

        unique_defects: list[dict[str, Any]] = []
        idx = 1

        for sig, items in groups.items():
            primary = items[0]
            count = len(items)
            defect_id = f"DEFECT-{idx:03d}"
            idx += 1

            test_titles = list(dict.fromkeys(item.get("test_title") or item.get("title", "Test") for item in items))
            classification = primary.get("classification") or (
                "CONFIRMED BUG" if any(item.get("confirmed") for item in items) else "POSSIBLE BUG"
            )

            unique_defects.append({
                "defect_id": defect_id,
                "signature": sig,
                "title": primary.get("title") or f"Defect on {primary.get('target', '/')}",
                "classification": classification,
                "severity": primary.get("severity", "high"),
                "category": primary.get("category", "functional"),
                "target": primary.get("target") or "/",
                "failed_assertion": primary.get("failed_assertion") or "page_loaded",
                "test_count": count,
                "seen_in_tests": test_titles,
                "display_badge": f"1 UNIQUE DEFECT (SEEN IN {count} TEST{'S' if count > 1 else ''})",
                "summary": primary.get("summary") or "",
                "likely_root_cause": primary.get("likely_root_cause") or "",
                "reproduction_steps": primary.get("reproduction_steps") or [],
                "evidence_references": primary.get("evidence_references") or [],
                "primary_failure_id": primary.get("id"),
                "reproduction_count": max((item.get("reproduction_count", 1) for item in items), default=1),
                "reproduction_total": max((item.get("reproduction_total", 1) for item in items), default=1),
            })

        return unique_defects
