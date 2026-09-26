"""API endpoints for querying Phase 3 deterministic test cases and test results."""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.log import Log
from app.models.test_case import TestCase, TestResult
from app.models.test_run import TestRun
from app.models.failure_analysis import FailureAnalysisRecord
from app.models.discovery import DiscoverySession
from app.models.project import Project
from app.services.deduplicator import DefectDeduplicator
from app.services.report_generator import QAReportGenerator

router = APIRouter(prefix="/api/test-runs", tags=["tests"])


@router.get("/{run_id}/test-cases")
async def list_test_cases(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    rows = (await db.execute(
        select(TestCase).where(TestCase.run_id == run_id).order_by(TestCase.created_at)
    )).scalars().all()
    return {
        "run_id": run_id,
        "total": len(rows),
        "test_cases": [
            {
                "id": tc.id,
                "type": tc.type,
                "title": tc.title,
                "priority": tc.priority,
                "source": getattr(tc, "source", "baseline"),
                "definition": tc.definition,
                "created_at": tc.created_at.isoformat() if tc.created_at else None,
            }
            for tc in rows
        ],
    }


@router.get("/{run_id}/test-cases/{test_case_id}")
async def get_test_case(run_id: str, test_case_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(TestCase).where(TestCase.run_id == run_id, TestCase.id == test_case_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Test case not found")
    return {
        "id": row.id,
        "run_id": row.run_id,
        "type": row.type,
        "title": row.title,
        "priority": row.priority,
        "source": getattr(row, "source", "baseline"),
        "definition": row.definition,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/{run_id}/test-results")
async def list_test_results(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    rows = (await db.execute(
        select(TestResult).where(TestResult.run_id == run_id).order_by(TestResult.created_at)
    )).scalars().all()
    return {
        "run_id": run_id,
        "total": len(rows),
        "passed": sum(1 for r in rows if r.status == "PASS"),
        "failed": sum(1 for r in rows if r.status != "PASS"),
        "test_results": [
            {
                "id": r.id,
                "test_case_id": r.test_case_id,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "error": r.error,
                "steps": r.steps_json,
                "assertions": r.assertions_json,
            }
            for r in rows
        ],
    }


@router.get("/{run_id}/test-results/{test_result_id}")
async def get_test_result(run_id: str, test_result_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(TestResult).where(TestResult.run_id == run_id, TestResult.id == test_result_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Test result not found")
    return {
        "id": row.id,
        "run_id": row.run_id,
        "test_case_id": row.test_case_id,
        "status": row.status,
        "duration_ms": row.duration_ms,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error": row.error,
        "steps": row.steps_json,
        "assertions": row.assertions_json,
    }


@router.get("/{run_id}/failures")
async def list_failures(run_id: str, db: AsyncSession = Depends(get_db)):
    """List all analyzed test failures for a test run."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")

    query = (
        select(FailureAnalysisRecord, TestResult, TestCase)
        .join(TestResult, FailureAnalysisRecord.test_result_id == TestResult.id)
        .join(TestCase, FailureAnalysisRecord.test_case_id == TestCase.id)
        .where(FailureAnalysisRecord.run_id == run_id)
        .order_by(FailureAnalysisRecord.created_at)
    )
    rows = (await db.execute(query)).all()

    return {
        "run_id": run_id,
        "total": len(rows),
        "failures": [
            {
                "id": fa.id,
                "run_id": fa.run_id,
                "test_result_id": fa.test_result_id,
                "test_case_id": fa.test_case_id,
                "test_title": tc.title,
                "test_type": tc.type,
                "test_source": getattr(tc, "source", "baseline"),
                "status": tr.status,
                "error": tr.error,
                "title": fa.title,
                "severity": fa.severity,
                "category": fa.category,
                "summary": fa.summary,
                "likely_root_cause": fa.likely_root_cause,
                "reproduction_steps": fa.reproduction_steps or [],
                "evidence_references": fa.evidence_references or [],
                "confidence": fa.confidence,
                "classification": getattr(fa, "classification", "POSSIBLE BUG") or "POSSIBLE BUG",
                "reproduction_count": getattr(fa, "reproduction_count", 1) or getattr(tr, "reproduction_count", 1),
                "reproduction_total": getattr(fa, "reproduction_total", 3) or getattr(tr, "reproduction_total", 3),
                "confirmed": getattr(tr, "confirmed", False),
                "http_status": getattr(tr, "http_status", None),
                "created_at": fa.created_at.isoformat() if fa.created_at else None,
            }
            for fa, tr, tc in rows
        ],
    }


@router.get("/{run_id}/failures/{failure_id}")
async def get_failure(run_id: str, failure_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single analyzed failure finding."""
    query = (
        select(FailureAnalysisRecord, TestResult, TestCase)
        .join(TestResult, FailureAnalysisRecord.test_result_id == TestResult.id)
        .join(TestCase, FailureAnalysisRecord.test_case_id == TestCase.id)
        .where(FailureAnalysisRecord.run_id == run_id, FailureAnalysisRecord.id == failure_id)
    )
    row = (await db.execute(query)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Failure analysis not found")

    fa, tr, tc = row
    return {
        "id": fa.id,
        "run_id": fa.run_id,
        "test_result_id": fa.test_result_id,
        "test_case_id": fa.test_case_id,
        "test_title": tc.title,
        "test_type": tc.type,
        "test_source": getattr(tc, "source", "baseline"),
        "status": tr.status,
        "error": tr.error,
        "title": fa.title,
        "severity": fa.severity,
        "category": fa.category,
        "summary": fa.summary,
        "likely_root_cause": fa.likely_root_cause,
        "reproduction_steps": fa.reproduction_steps or [],
        "evidence_references": fa.evidence_references or [],
        "confidence": fa.confidence,
        "classification": getattr(fa, "classification", "POSSIBLE BUG") or "POSSIBLE BUG",
        "reproduction_count": getattr(fa, "reproduction_count", 1) or getattr(tr, "reproduction_count", 1),
        "reproduction_total": getattr(fa, "reproduction_total", 3) or getattr(tr, "reproduction_total", 3),
        "confirmed": getattr(tr, "confirmed", False),
        "http_status": getattr(tr, "http_status", None),
        "created_at": fa.created_at.isoformat() if fa.created_at else None,
    }


@router.get("/{run_id}/deduplicated-defects")
async def list_deduplicated_defects(run_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve deterministically deduplicated defects for a test run."""
    failures_resp = await list_failures(run_id, db)
    failures = failures_resp.get("failures", [])
    unique_defects = DefectDeduplicator.deduplicate(failures)
    return {
        "run_id": run_id,
        "total_failures": len(failures),
        "total_unique_defects": len(unique_defects),
        "defects": unique_defects,
    }


@router.get("/{run_id}/observations")
async def list_observations(run_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve runtime observations for a test run."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    obs = getattr(run, "observations", None) or []
    return {
        "run_id": run_id,
        "total": len(obs),
        "observations": obs,
    }


@router.get("/{run_id}/report")
async def get_qa_report(run_id: str, db: AsyncSession = Depends(get_db)):
    """Generate structured JSON QA Report."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")

    project = await db.get(Project, run.project_id)
    project_data = {
        "repository_url": project.repository_url if project else run.branch,
        "detected_framework": getattr(project, "detected_framework", None) or (run.detected_config or {}).get("framework", "Node.js / Express"),
    }

    # Application surface from discovery session
    discovery_session = (await db.execute(
        select(DiscoverySession).where(DiscoverySession.run_id == run_id)
    )).scalar_one_or_none()
    app_map = discovery_session.application_map if discovery_session else {}
    routes = [p.get("url") for p in app_map.get("pages", []) if isinstance(p, dict)]
    forms_count = sum(len(p.get("forms", [])) for p in app_map.get("pages", []) if isinstance(p, dict))
    inputs_count = sum(sum(len(f.get("inputs", [])) for f in p.get("forms", [])) for p in app_map.get("pages", []) if isinstance(p, dict))
    api_endpoints = [e.get("path") for e in app_map.get("api_endpoints", []) if isinstance(e, dict)]

    surface = {
        "pages_count": len(routes),
        "routes": routes,
        "forms_count": forms_count,
        "inputs_count": inputs_count,
        "api_endpoints": api_endpoints,
    }

    # Test summary
    tc_rows = (await db.execute(select(TestCase).where(TestCase.run_id == run_id))).scalars().all()
    tr_rows = (await db.execute(select(TestResult).where(TestResult.run_id == run_id))).scalars().all()
    test_summary = {
        "total": len(tr_rows),
        "passed": sum(1 for r in tr_rows if r.status == "PASS"),
        "failed": sum(1 for r in tr_rows if r.status in ("FAIL", "ERROR", "TIMEOUT")),
        "errors": sum(1 for r in tr_rows if r.status == "ERROR"),
        "timeouts": sum(1 for r in tr_rows if r.status == "TIMEOUT"),
        "baseline_count": sum(1 for tc in tc_rows if getattr(tc, "source", "") == "baseline"),
        "demo_deterministic_count": sum(1 for tc in tc_rows if getattr(tc, "source", "") == "demo_deterministic"),
        "ai_generated_count": sum(1 for tc in tc_rows if getattr(tc, "source", "") == "ai"),
    }

    failures_resp = await list_failures(run_id, db)
    findings = failures_resp.get("failures", [])
    unique_defects = DefectDeduplicator.deduplicate(findings)

    run_dict = {
        "id": run.id,
        "status": run.status,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": (run.finished_at - run.started_at).total_seconds() if run.finished_at and run.started_at else 0.0,
        "ai_status": run.ai_status,
        "ai_model": run.ai_model,
        "ai_warning": run.ai_warning,
        "detected_config": run.detected_config or {},
    }

    report = QAReportGenerator.generate_json_report(
        run_data=run_dict,
        project_data=project_data,
        application_surface=surface,
        test_summary=test_summary,
        runtime_observations=getattr(run, "observations", None) or [],
        static_findings=getattr(run, "static_findings", None) or {},
        findings=findings,
        unique_defects=unique_defects,
    )
    return report


@router.get("/{run_id}/report/html", response_class=HTMLResponse)
async def get_qa_report_html(run_id: str, db: AsyncSession = Depends(get_db)):
    """Generate and return standalone HTML QA Audit Report."""
    report_json = await get_qa_report(run_id, db)
    html_content = QAReportGenerator.generate_html_report(report_json)
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/{run_id}/strategy")
async def get_strategy(run_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve the AI QA Test Strategy for a test run."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")

    log_row = (await db.execute(
        select(Log).where(Log.run_id == run_id, Log.source == "ai_strategy").order_by(Log.timestamp.desc())
    )).scalars().first()

    if log_row:
        try:
            return json.loads(log_row.message)
        except Exception:
            pass

    tc_rows = (await db.execute(
        select(TestCase).where(TestCase.run_id == run_id, TestCase.source == "ai")
    )).scalars().all()

    items = []
    for i, tc in enumerate(tc_rows):
        cat = "navigation"
        target = "/"
        if isinstance(tc.definition, dict):
            steps = tc.definition.get("steps") or []
            if steps and isinstance(steps[0], dict) and steps[0].get("target"):
                target = steps[0].get("target")
            if "cart" in target or "checkout" in target:
                cat = "navigation"
            elif "api" in target:
                cat = "api"
            elif "login" in target or "auth" in target:
                cat = "authentication"
        items.append({
            "id": f"STRAT-{i+1:03d}",
            "category": cat,
            "target": target,
            "description": f"AI strategic test target for {tc.title}",
            "risk_level": tc.priority or "high",
            "priority": tc.priority or "high",
        })

    return {
        "run_id": run_id,
        "summary": "AI Test Planning strategy targeting critical user flows, navigation, and API contracts",
        "items": items,
        "total": len(items),
    }

