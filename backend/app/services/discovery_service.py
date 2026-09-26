"""Host orchestration of the controlled same-container discovery process."""
import base64
import json
import shlex
import uuid

from sqlalchemy import select
from docker.errors import NotFound

from app.config import settings
from app.models.discovery import DiscoverySession
from app.models.log import Log
from app.services.evidence_manager import EvidenceManager
from testq_browser.schemas import ApplicationMap,DiscoveryRequest,Observation,now
from testq_browser.policies import redact


class DiscoveryError(RuntimeError):
    pass


class DiscoveryService:
    def __init__(self, db, sandbox, container_id, control, blocking):
        self.db,self.sandbox,self.container_id = db,sandbox,container_id
        self.control,self.blocking = control,blocking
        self.evidence = EvidenceManager(db)
        self.session = None
        self.result = None

    async def discover(self, base_url: str, run_id: str, limits=None) -> ApplicationMap:
        request = DiscoveryRequest(base_url=base_url,run_id=run_id,session_id=str(uuid.uuid4()),
                                   limits=limits or settings.discovery_limits())
        self.evidence.max_artifact_bytes = request.limits.max_artifact_bytes
        self.evidence.max_evidence_bytes = request.limits.max_evidence_bytes
        self.result = ApplicationMap(run_id=run_id,session_id=request.session_id,base_url=request.base_url,limits=request.limits)
        self.session = DiscoverySession(id=request.session_id,run_id=run_id,
                                        application_map=self.result.model_dump(mode="json"))
        self.db.add(self.session)
        await self.db.commit()
        error = None
        execution = None
        try:
            payload = base64.b64encode(request.model_dump_json().encode()).decode()
            execution = await self.blocking(self.sandbox.execute,self.container_id,
                "/opt/testq/venv/bin/python -I -m testq_browser.runner " + shlex.quote(payload),
                timeout=request.limits.discovery_timeout+15,working_dir="/opt/testq",source="discovery",
                user="10002:10002",environment={"HOME":"/home/browser","PYTHONNOUSERSITE":"1"})
        except BaseException as caught:
            error = caught
        finally:
            # No cancellation checkpoint here: export must run even after a hard kill.
            try:
                data = await self.blocking(self.sandbox.read_artifact,self.container_id,request.session_id,
                                           "result.json",request.limits.max_artifact_bytes)
                result = ApplicationMap.model_validate_json(data)
                if (result.run_id,result.session_id,result.base_url) != (run_id,request.session_id,request.base_url):
                    raise DiscoveryError("Discovery result context mismatch")
                result.limits = request.limits
                self.result = result
            except Exception as caught:
                self.result.status = "failed"
                self.result.error = "Discovery result unavailable: " + redact(str(caught))
            if self.control.cancel_event.is_set():
                self.result.status = "cancelled"
                self.result.error = "Discovery cancelled"
            elif error or (execution and execution.timed_out):
                self.result.status = "timed_out" if isinstance(error,TimeoutError) or (execution and execution.timed_out) else "failed"
                self.result.error = redact(str(error) if error else "Discovery process exceeded its time limit")
            elif self.result.status == "running" or (execution and execution.exit_code != 0 and self.result.status=="completed"):
                self.result.status = "failed"
                self.result.error = "Discovery process exited before completion"
            self.result.finished_at = self.result.finished_at or now()
            await self.persist()
            total = 0
            names = set()
            for item in self.result.artifacts:
                try:
                    total += item.size_bytes
                    if item.filename in names or total > request.limits.max_evidence_bytes or item.size_bytes > request.limits.max_artifact_bytes:
                        raise DiscoveryError("Invalid artifact manifest or evidence budget")
                    names.add(item.filename)
                    data = await self.blocking(self.sandbox.read_artifact,self.container_id,request.session_id,
                                               item.filename,request.limits.max_artifact_bytes)
                    await self.evidence.store(run_id,request.session_id,item,data)
                except Exception as caught:
                    self.result.status = "failed" if self.result.status == "completed" else self.result.status
                    self.result.error = "Evidence export failed: " + redact(str(caught))
                    if len(self.result.observations)<request.limits.max_observations:
                        self.result.observations.append(Observation(run_id=run_id,session_id=request.session_id,
                            page_url=base_url,kind="evidence_error",message=self.result.error[:4000]))
            await self.persist()
            await self.evidence.store_json(run_id,request.session_id,"application-map.json","application_map",
                                           self.result.model_dump(mode="json"))
        if error:
            raise error
        if self.result.status != "completed":
            raise DiscoveryError(self.result.error or f"Discovery {self.result.status}")
        return self.result

    async def persist(self):
        self.session.status = self.result.status
        self.session.application_map = self.result.model_dump(mode="json")
        self.session.finished_at = self.result.finished_at
        await self.db.commit()

    async def attach_application_logs(self):
        if self.session is None:
            return
        logs = (await self.db.execute(select(Log).where(Log.run_id==self.session.run_id,Log.source=="application"))).scalars().all()
        entries = []
        size = 1024
        for row in logs:
            entry = {"log_id":row.id,"timestamp":row.timestamp.isoformat(),"level":row.level,
                     "message":redact(row.message,65536)}
            size += len(json.dumps(entry,ensure_ascii=False,indent=2).encode()) + 64
            if size > self.evidence.max_artifact_bytes:
                break
            entries.append(entry)
        await self.evidence.store_json(self.session.run_id,self.session.id,"application-logs.json","application_log",
            {"run_id":self.session.run_id,"session_id":self.session.id,"source":"application",
             "logs":entries,"truncated":len(entries)<len(logs)})
