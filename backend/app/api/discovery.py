"""Read-only discovery maps and verified per-run evidence retrieval."""
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.config import settings
from app.database import get_db
from app.models.discovery import DiscoverySession,Evidence
from app.services.evidence_manager import verify_artifact, verify_test_artifact, EvidenceError
from testq_browser.schemas import ApplicationMap, Artifact

router = APIRouter(prefix="/api/test-runs", tags=["discovery"])


@router.get("/{run_id}/discovery", response_model=ApplicationMap)
async def discovery_map(run_id: str, db=Depends(get_db)):
    session = (await db.execute(select(DiscoverySession).where(DiscoverySession.run_id == run_id))).scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Discovery has not started for this run")
    return ApplicationMap.model_validate(session.application_map)


@router.get("/{run_id}/evidence")
async def list_evidence(run_id: str, db=Depends(get_db)):
    await discovery_map(run_id, db)
    rows = (await db.execute(select(Evidence).where(Evidence.run_id == run_id).order_by(Evidence.created_at))).scalars().all()
    return {
        "run_id": run_id,
        "evidence": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "test_result_id": r.test_result_id,
                "page_url": r.page_url,
                "kind": r.kind,
                "size_bytes": r.size_bytes,
                "sha256": r.sha256,
                "media_type": r.media_type,
                "url": f"/api/test-runs/{run_id}/evidence/{r.id}",
            }
            for r in rows
        ],
    }


@router.get("/{run_id}/evidence/{evidence_id}")
async def artifact_file(run_id: str, evidence_id: str, db=Depends(get_db)):
    row = (await db.execute(select(Evidence).where(Evidence.id == evidence_id, Evidence.run_id == run_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Evidence not found")
    root = Path(settings.evidence_dir).resolve()
    path = (root / row.path).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != row.size_bytes:
        raise HTTPException(410, "Evidence missing or changed")
    try:
        raw_bytes = path.read_bytes()
        if row.kind.startswith("test_"):
            verify_test_artifact(raw_bytes, row.kind, path.name)
        else:
            verify_artifact(raw_bytes, Artifact(filename=path.name, kind=row.kind, page_url=row.page_url,
                size_bytes=row.size_bytes, sha256=row.sha256, media_type=row.media_type))
    except (EvidenceError, ValueError):
        raise HTTPException(410, "Evidence verification failed")
    return FileResponse(path, media_type=row.media_type, filename=path.name,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
