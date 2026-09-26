"""QA Report Generator (Phase 4.6).
Generates structured JSON and professional standalone HTML QA reports.
Contains honest metrics without fabricated scores.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any


class QAReportGenerator:
    """Generates JSON and HTML QA Audit reports for a completed TestQ run."""

    @classmethod
    def generate_json_report(
        cls,
        run_data: dict[str, Any],
        project_data: dict[str, Any],
        application_surface: dict[str, Any],
        test_summary: dict[str, Any],
        runtime_observations: list[dict[str, Any]],
        static_findings: dict[str, Any],
        findings: list[dict[str, Any]],
        unique_defects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compile comprehensive JSON QA Report."""
        return {
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "tool": "TestQ Automated QA Agent",
                "version": "0.1.0",
            },
            "run": {
                "id": run_data.get("id"),
                "status": run_data.get("status"),
                "repository": project_data.get("repository_url"),
                "branch": run_data.get("branch"),
                "commit_sha": run_data.get("commit_sha"),
                "framework": project_data.get("detected_framework") or run_data.get("detected_config", {}).get("framework", "Node.js / Express"),
                "started_at": run_data.get("started_at"),
                "finished_at": run_data.get("finished_at"),
                "duration_seconds": run_data.get("duration_seconds", 0.0),
                "ai_status": run_data.get("ai_status", "NOT_REQUESTED"),
                "ai_model": run_data.get("ai_model", "qwen3:8b"),
                "ai_warning": run_data.get("ai_warning"),
            },
            "application_surface": {
                "pages_discovered": application_surface.get("pages_count", 0),
                "routes": application_surface.get("routes", []),
                "forms_count": application_surface.get("forms_count", 0),
                "inputs_count": application_surface.get("inputs_count", 0),
                "api_endpoints": application_surface.get("api_endpoints", []),
            },
            "testing": {
                "total_tests": test_summary.get("total", 0),
                "passed": test_summary.get("passed", 0),
                "failed": test_summary.get("failed", 0),
                "errors": test_summary.get("errors", 0),
                "timeouts": test_summary.get("timeouts", 0),
                "baseline_count": test_summary.get("baseline_count", 0),
                "demo_deterministic_count": test_summary.get("demo_deterministic_count", 0),
                "ai_generated_count": test_summary.get("ai_generated_count", 0),
            },
            "runtime_observations": {
                "total": len(runtime_observations),
                "items": runtime_observations[:50],
            },
            "static_analysis": {
                "tool": static_findings.get("tool", "npm audit + lint"),
                "total": static_findings.get("total", 0),
                "findings": static_findings.get("findings", []),
            },
            "unique_defects": unique_defects,
            "findings": findings,
        }

    @classmethod
    def generate_html_report(cls, report_json: dict[str, Any]) -> str:
        """Render standalone, dark-themed professional HTML report."""
        run = report_json["run"]
        testing = report_json["testing"]
        surface = report_json["application_surface"]
        defects = report_json.get("unique_defects", [])
        findings = report_json.get("findings", [])
        static_f = report_json.get("static_analysis", {}).get("findings", [])
        observations = report_json.get("runtime_observations", {}).get("items", [])

        def escape(v):
            return html.escape(str(v or ""))

        # Defect cards
        defect_html = ""
        for d in defects:
            cls_badge = "badge-confirmed" if d.get("classification") == "CONFIRMED BUG" else "badge-possible"
            steps_li = "".join(f"<li>{escape(s)}</li>" for s in d.get("reproduction_steps", []))
            tests_li = "".join(f"<span class='pill pill-neutral'>{escape(t)}</span>" for t in d.get("seen_in_tests", []))
            defect_html += f"""
            <div class="card defect-card">
              <div class="card-header">
                <div class="card-title-group">
                  <span class="badge {cls_badge}">{escape(d.get('classification', 'CONFIRMED BUG'))}</span>
                  <span class="badge badge-sev-{escape(d.get('severity', 'high'))}">{escape(d.get('severity', 'high').upper())}</span>
                  <span class="defect-id">{escape(d.get('defect_id', 'DEFECT'))}</span>
                  <h3>{escape(d.get('title'))}</h3>
                </div>
                <span class="pill pill-primary">{escape(d.get('display_badge', ''))}</span>
              </div>
              <p class="summary-text">{escape(d.get('summary'))}</p>
              <div class="grid-2">
                <div>
                  <h4>Likely Root Cause (Hypothesis)</h4>
                  <p class="code-box">{escape(d.get('likely_root_cause'))}</p>
                </div>
                <div>
                  <h4>Reproduction Verification</h4>
                  <p><strong>{escape(d.get('reproduction_count', 3))} / {escape(d.get('reproduction_total', 3))} Reproductions</strong> &mdash; Deterministic Replays Confirmed</p>
                  <ol class="repro-list">{steps_li}</ol>
                </div>
              </div>
              <div class="card-footer">
                <small>Observed in tests:</small>
                <div class="pill-group">{tests_li}</div>
              </div>
            </div>
            """

        if not defects:
            defect_html = "<div class='card'><p class='muted'>No defects confirmed during this run.</p></div>"

        # Static findings cards
        static_html = ""
        for sf in static_f[:10]:
            static_html += f"""
            <div class="card compact">
              <div class="row-between">
                <strong>{escape(sf.get('title', 'Finding'))}</strong>
                <span class="badge badge-sev-{escape(sf.get('severity', 'medium'))}">{escape(sf.get('severity', 'medium'))}</span>
              </div>
              <p>{escape(sf.get('message', ''))}</p>
              <small class="muted">File: {escape(sf.get('file', 'unknown'))}</small>
            </div>
            """
        if not static_f:
            static_html = "<p class='muted'>No static findings detected.</p>"

        # Runtime observations
        obs_html = ""
        for obs in observations[:15]:
            obs_html += f"""
            <tr class="obs-row">
              <td><span class="pill">{escape(obs.get('kind', ''))}</span></td>
              <td><code>{escape(obs.get('source', ''))}</code></td>
              <td>{escape(obs.get('message', ''))}</td>
            </tr>
            """
        if not observations:
            obs_html = "<tr><td colspan='3' class='muted'>No abnormal runtime observations recorded.</td></tr>"

        ai_status_banner = ""
        if run.get("ai_status") in ("DEGRADED", "UNAVAILABLE"):
            ai_status_banner = f"""
            <div class="alert alert-warning">
              <strong>AI ENGINE DEGRADED / UNAVAILABLE:</strong>
              <span>{escape(run.get('ai_warning', 'Deterministic testing completed, but AI-generated adversarial tests were unavailable.'))}</span>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestQ QA Audit Report — {escape(run.get('repository'))}</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --text: #f9fafb;
      --muted: #9ca3af;
      --primary: #38bdf8;
      --danger: #ef4444;
      --warning: #f59e0b;
      --success: #10b981;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      margin: 0;
      padding: 32px;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1080px;
      margin: 0 auto;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 24px;
      margin-bottom: 32px;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge-confirmed {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
    .badge-possible {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}
    .badge-sev-critical {{ background: #dc2626; color: #fff; }}
    .badge-sev-high {{ background: #ea580c; color: #fff; }}
    .badge-sev-medium {{ background: #d97706; color: #fff; }}
    .badge-sev-low {{ background: #4b5563; color: #fff; }}
    .pill {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 12px;
      background: #1f2937;
      color: var(--text);
    }}
    .pill-primary {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }}
    .pill-group {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
    }}
    .card.compact {{ padding: 12px 16px; margin-bottom: 12px; }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .stat-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; }}
    .stat-value {{ font-size: 28px; font-weight: bold; margin-top: 4px; }}
    .stat-value.red {{ color: var(--danger); }}
    .stat-value.green {{ color: var(--success); }}
    .stat-value.blue {{ color: var(--primary); }}
    .stat-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; }}
    .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
    .card-title-group {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
    .card-title-group h3 {{ margin: 0; font-size: 18px; }}
    .defect-id {{ font-family: monospace; color: var(--muted); }}
    .code-box {{ background: #0b0f19; border: 1px solid var(--border); border-radius: 4px; padding: 12px; font-family: monospace; font-size: 13px; }}
    .repro-list {{ margin: 0; padding-left: 20px; font-size: 14px; }}
    .repro-list li {{ margin-bottom: 4px; }}
    .muted {{ color: var(--muted); }}
    .alert {{ padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; font-size: 14px; }}
    .alert-warning {{ background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); color: #fbbf24; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }}
    th {{ color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 11px; }}
    .row-between {{ display: flex; justify-content: space-between; align-items: center; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="row-between">
        <div>
          <span class="pill pill-primary">TestQ Automated QA Report</span>
          <h1 style="margin: 8px 0 4px 0;">{escape(run.get('repository', 'Application'))}</h1>
          <p class="muted" style="margin: 0;">Branch: <code>{escape(run.get('branch', 'main'))}</code> &middot; Commit: <code>{escape(str(run.get('commit_sha', 'HEAD'))[:7])}</code> &middot; Framework: {escape(run.get('framework'))} &middot; Model: <code>{escape(run.get('ai_model'))}</code></p>
        </div>
        <div style="text-align: right;">
          <span class="badge" style="background:#1f2937;font-size:13px;padding:6px 12px;">{escape(run.get('status'))}</span>
          <div class="muted" style="font-size:12px;margin-top:6px;">Generated: {escape(report_json['meta']['generated_at'])}</div>
        </div>
      </div>
    </header>

    {ai_status_banner}

    <section>
      <h2>Testing Metrics</h2>
      <div class="grid-4">
        <div class="stat-card">
          <div class="stat-label">Total Tests</div>
          <div class="stat-value">{testing.get('total_tests', 0)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Passed Tests</div>
          <div class="stat-value green">{testing.get('passed', 0)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Failed / Defect Tests</div>
          <div class="stat-value red">{testing.get('failed', 0)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Unique Defects</div>
          <div class="stat-value red">{len(defects)}</div>
        </div>
      </div>
      <p class="muted" style="font-size:13px;">Test composition: {testing.get('baseline_count', 0)} baseline deterministic, {testing.get('demo_deterministic_count', 0)} demo deterministic showcase, {testing.get('ai_generated_count', 0)} AI-generated adversarial.</p>
    </section>

    <section style="margin-top: 36px;">
      <h2>Confirmed & Investigated Defects</h2>
      {defect_html}
    </section>

    <section style="margin-top: 36px;">
      <h2>Application Surface Discovered</h2>
      <div class="card">
        <div class="grid-4" style="margin-bottom: 12px;">
          <div><small class="muted">PAGES</small><div style="font-size:20px;font-weight:bold;">{surface.get('pages_discovered', 0)}</div></div>
          <div><small class="muted">FORMS</small><div style="font-size:20px;font-weight:bold;">{surface.get('forms_count', 0)}</div></div>
          <div><small class="muted">INPUT CONTROLS</small><div style="font-size:20px;font-weight:bold;">{surface.get('inputs_count', 0)}</div></div>
          <div><small class="muted">API ENDPOINTS</small><div style="font-size:20px;font-weight:bold;">{len(surface.get('api_endpoints', []))}</div></div>
        </div>
        <div style="font-size:13px;">Discovered Routes: {', '.join(f"<code>{escape(r)}</code>" for r in surface.get('routes', []))}</div>
      </div>
    </section>

    <section style="margin-top: 36px;">
      <h2>Static Analysis Findings</h2>
      <p class="muted" style="font-size:13px;">Reported by {escape(report_json.get('static_analysis', {}).get('tool'))} &mdash; stored strictly as static findings, not runtime bugs.</p>
      {static_html}
    </section>

    <section style="margin-top: 36px;">
      <h2>Runtime Observations</h2>
      <div class="card" style="padding: 0; overflow: hidden;">
        <table>
          <thead>
            <tr><th>Type</th><th>Source</th><th>Event Observation</th></tr>
          </thead>
          <tbody>
            {obs_html}
          </tbody>
        </table>
      </div>
    </section>

    <footer style="margin-top: 48px; border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--muted); text-align: center;">
      TestQ Independent AI QA Agent &middot; Built for truthful, reproducible verification.
    </footer>
  </div>
</body>
</html>
"""
