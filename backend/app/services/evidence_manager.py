"""Export verified bounded artifacts; never extract untrusted archive paths."""
import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path
from sqlalchemy import select

from app.config import settings
from app.models.discovery import Evidence
from testq_browser.schemas import Artifact


class EvidenceError(ValueError):
    pass


def verify_artifact(data: bytes, item: Artifact):
    if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
        raise EvidenceError("Evidence size/hash mismatch")
    if item.kind == "screenshot":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
            raise EvidenceError("Invalid PNG evidence")
        width,height = struct.unpack(">II",data[16:24])
        if width > 1280 or height > 720 or min(width,height) <= 0:
            raise EvidenceError("Screenshot dimensions exceed viewport")
    elif item.kind == "trace":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if not entries or len(entries)>100 or sum(e.file_size for e in entries)>10*1024**2:
                raise EvidenceError("Trace expansion budget exceeded")
            for entry in entries:
                if "/" in entry.filename or "\\" in entry.filename or not entry.filename.endswith((".trace",".network")):
                    raise EvidenceError("Unexpected trace entry")
                if entry.filename.endswith(".network") and entry.file_size:
                    raise EvidenceError("Raw network trace is prohibited")
                if entry.filename.endswith(".trace"):
                    for line in archive.read(entry).splitlines():
                        event = json.loads(line)
                        if event.get("type") not in {"context-options","before","after"}:
                            raise EvidenceError("Unexpected trace event")
    else:
        json.loads(data)


def verify_test_artifact(data: bytes, kind: str, filename: str):
    """Verify a Phase 3 test artifact without requiring a discovery Artifact model."""
    from app.schemas.test_case import TestArtifact
    sha = hashlib.sha256(data).hexdigest()
    media = {".png": "image/png", ".zip": "application/zip", ".json": "application/json"}
    suffix = Path(filename).suffix
    item = TestArtifact(kind=kind, filename=filename, size_bytes=len(data),
                        sha256=sha, media_type=media.get(suffix, "application/octet-stream"))
    if kind == "test_screenshot":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
            raise EvidenceError("Invalid PNG test evidence")
        width, height = struct.unpack(">II", data[16:24])
        if width > 1280 or height > 720 or min(width, height) <= 0:
            raise EvidenceError("Test screenshot dimensions exceed viewport")
    elif kind in ("test_console", "test_network", "test_error", "test_result"):
        json.loads(data)
    # test_trace validated like discovery trace if needed
    return item


class EvidenceManager:
    def __init__(self, db, root=None):
        self.db = db
        self.root = Path(root or settings.evidence_dir).resolve()
        self.max_artifact_bytes = 8 * 1024**2
        self.max_evidence_bytes = 64 * 1024**2

    def directory(self, run_id, session_id):
        """Discovery evidence directory — preserves Phase 2 path structure."""
        import re
        if not all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",x) for x in (run_id,session_id)):
            raise EvidenceError("Invalid evidence context")
        path = (self.root/run_id/"discovery"/session_id).resolve()
        if not path.is_relative_to(self.root):
            raise EvidenceError("Evidence path escapes root")
        path.mkdir(parents=True,exist_ok=True)
        return path

    def test_directory(self, run_id, context_id):
        """Phase 3 test evidence directory: evidence/{run_id}/testing/{context_id}/"""
        import re
        if not all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", x) for x in (run_id, context_id)):
            raise EvidenceError("Invalid test evidence context")
        path = (self.root / run_id / "testing" / context_id).resolve()
        if not path.is_relative_to(self.root):
            raise EvidenceError("Test evidence path escapes root")
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def store(self, run_id, session_id, item, data):
        if len(data) > self.max_artifact_bytes:
            raise EvidenceError("Artifact exceeds export budget")
        verify_artifact(data,item)
        directory = self.directory(run_id,session_id)
        retained = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
        if retained + len(data) > self.max_evidence_bytes:
            raise EvidenceError("Session evidence exceeds export budget")
        path = directory/item.filename
        if path.is_symlink():
            raise EvidenceError("Evidence path is a symlink")
        temp = path.with_suffix(path.suffix+".tmp")
        # Write to temp file then replace target
        with temp.open("wb") as stream:
            stream.write(data)
        temp.replace(path)
        # Verify actual exported bytes before recording metadata.
        verify_artifact(path.read_bytes(),item)
        path_str = path.relative_to(self.root).as_posix()
        existing = (await self.db.execute(select(Evidence).where(Evidence.path == path_str))).scalar_one_or_none()
        if existing:
            existing.size_bytes = item.size_bytes
            existing.sha256 = item.sha256
            existing.media_type = item.media_type
            row = existing
        else:
            row = Evidence(run_id=run_id,session_id=session_id,page_url=item.page_url,kind=item.kind,
                           path=path_str,size_bytes=item.size_bytes,
                           sha256=item.sha256,media_type=item.media_type)
            self.db.add(row)
        await self.db.commit()
        return row

    async def store_test(self, run_id, session_id, test_result_id, filename, kind, data):
        """Store Phase 3 test evidence with test_result_id linkage."""
        if len(data) > self.max_artifact_bytes:
            raise EvidenceError("Test artifact exceeds export budget")
        item = verify_test_artifact(data, kind, filename)
        directory = self.test_directory(run_id, test_result_id)
        retained = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
        if retained + len(data) > self.max_evidence_bytes:
            raise EvidenceError("Test evidence exceeds export budget")
        path = directory / filename
        if path.is_symlink():
            raise EvidenceError("Test evidence path is a symlink")
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("wb") as stream:
            stream.write(data)
        temp.replace(path)
        path_str = path.relative_to(self.root).as_posix()
        existing = (await self.db.execute(select(Evidence).where(Evidence.path == path_str))).scalar_one_or_none()
        if existing:
            existing.size_bytes = item.size_bytes
            existing.sha256 = item.sha256
            existing.media_type = item.media_type
            row = existing
        else:
            row = Evidence(run_id=run_id, session_id=session_id,
                           test_result_id=test_result_id, page_url=item.page_url,
                           kind=item.kind,
                           path=path_str,
                           size_bytes=item.size_bytes, sha256=item.sha256,
                           media_type=item.media_type)
            self.db.add(row)
        await self.db.commit()
        return row

    async def store_test_json(self, run_id, session_id, test_result_id, filename, kind, payload):
        """Store JSON test evidence."""
        data = json.dumps(payload, indent=2, ensure_ascii=False).encode()
        return await self.store_test(run_id, session_id, test_result_id, filename, kind, data)

    async def store_json(self,run_id,session_id,filename,kind,payload):
        data = json.dumps(payload,indent=2,ensure_ascii=False).encode()
        item = Artifact(kind=kind,filename=filename,size_bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),media_type="application/json")
        return await self.store(run_id,session_id,item,data)

