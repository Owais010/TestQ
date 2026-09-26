"""Practical Static Analysis Service (Phase 4.6).
Performs static analysis on Node/React/Next projects:
1. npm audit (dependency vulnerabilities)
2. Static code & configuration patterns scan
Static findings are kept separate from confirmed application bugs.
Show: STATIC FINDINGS, not BUGS.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("testq.static_analyzer")


class StaticAnalyzer:
    """Executes safe, bounded static analysis on project workspace."""

    @classmethod
    def analyze_project(cls, repo_path: Path | str) -> dict[str, Any]:
        """Perform static analysis on cloned project files.
        Returns:
            Dict containing 'tool', 'total', 'summary', and list of 'findings'.
        """
        path = Path(repo_path).resolve()
        findings: list[dict[str, Any]] = []
        counter = 1

        # 1. Dependency Audit (npm audit if package-lock or package.json exists)
        pkg_json = path / "package.json"
        if pkg_json.exists():
            audit_findings = cls._run_npm_audit(path)
            for item in audit_findings:
                item["id"] = f"STATIC-{counter:03d}"
                counter += 1
                findings.append(item)

        # 2. Static Code / Pattern Scanning (Hardcoded secrets, unsafe patterns, input validation)
        code_findings = cls._scan_code_patterns(path)
        for item in code_findings:
            item["id"] = f"STATIC-{counter:03d}"
            counter += 1
            findings.append(item)

        summary = f"{len(findings)} static finding{'s' if len(findings) != 1 else ''} identified"
        return {
            "tool": "TestQ Static Analyzer (audit + lint)",
            "total": len(findings),
            "summary": summary,
            "findings": findings,
        }

    @classmethod
    def _run_npm_audit(cls, path: Path) -> list[dict[str, Any]]:
        """Run npm audit --json on project directory if package-lock.json exists."""
        findings: list[dict[str, Any]] = []
        lock_file = path / "package-lock.json"
        if not lock_file.exists():
            return findings

        try:
            cmd = ["npm", "audit", "--json"]
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            res = subprocess.run(
                cmd,
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=30,
                **options,
            )
            data = json.loads(res.stdout or "{}")
            vulns = data.get("vulnerabilities", {})
            for name, details in list(vulns.items())[:15]:
                severity = details.get("severity", "moderate")
                findings.append({
                    "type": "dependency_audit",
                    "category": "security_dependency",
                    "severity": severity,
                    "title": f"Vulnerable dependency: {name}",
                    "file": "package.json",
                    "message": f"Package '{name}' has known severity={severity} vulnerability. Fix available: {details.get('fixAvailable', False)}",
                    "rule": "npm-audit",
                })
        except Exception as e:
            logger.debug("npm audit skipped or failed: %s", e)

        return findings

    @classmethod
    def _scan_code_patterns(cls, path: Path) -> list[dict[str, Any]]:
        """Scan source files for common security and quality patterns."""
        findings: list[dict[str, Any]] = []
        extensions = {".js", ".jsx", ".ts", ".tsx", ".py", ".json"}

        # Patterns to check
        patterns = [
            (
                r"(?:jwt-token-xyz|mock-jwt-token|secret[_-]?key\s*=\s*['\"][^'\"]+['\"])",
                "Hardcoded credential or token placeholder found in source",
                "security_credential",
                "high",
                "hardcoded-credential",
            ),
            (
                r"eval\s*\(",
                "Unsafe eval() invocation detected",
                "code_injection",
                "critical",
                "no-eval",
            ),
            (
                r"http://localhost:\d+",
                "Hardcoded local loopback URL in application code",
                "configuration",
                "low",
                "hardcoded-endpoint",
            ),
        ]

        try:
            for root, dirs, files in os.walk(path):
                # Skip node_modules and .git
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "venv", ".next", "dist")]
                for f in files:
                    file_path = Path(root) / f
                    if file_path.suffix.lower() not in extensions:
                        continue
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue

                    rel_path = file_path.relative_to(path).as_posix()
                    for regex, msg, category, severity, rule in patterns:
                        match = re.search(regex, content, re.IGNORECASE)
                        if match:
                            line_no = content[:match.start()].count("\n") + 1
                            findings.append({
                                "type": "code_quality",
                                "category": category,
                                "severity": severity,
                                "title": f"Static Pattern: {rule}",
                                "file": rel_path,
                                "line": line_no,
                                "message": f"{msg} (line {line_no})",
                                "rule": rule,
                            })
                            if len(findings) >= 20:
                                return findings
        except Exception as e:
            logger.debug("Code pattern scan failed: %s", e)

        return findings
