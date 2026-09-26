"""Bounded screenshots and sanitized Playwright action traces."""
import hashlib
import json
import zipfile
from pathlib import Path
from .schemas import Artifact
from .policies import redact, safe_url


class EvidenceLimit(Exception):
    pass


def sanitize_trace(source, destination, limit):
    """Keep the trace timeline, never network bodies/headers, DOM or source files."""
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as outgoing:
        total = 0
        for entry in incoming.infolist():
            if not entry.filename.endswith(".trace") or entry.file_size > limit:
                continue
            lines = []
            for line in incoming.read(entry).splitlines():
                event = json.loads(line)
                if event.get("type") not in {"context-options", "before", "after"}:
                    continue
                allowed = {"type","version","origin","browserName","platform","wallTime","monotonicTime",
                           "callId","startTime","endTime","class","method","apiName","pageId","contextId"}
                safe = {key:redact(value) if isinstance(value,str) else value for key,value in event.items()
                        if key in allowed and isinstance(value,(str,int,float,bool,type(None)))}
                if event.get("type") == "context-options":
                    safe["options"] = {"viewport":{"width":1280,"height":720}}
                if event.get("type") == "before":
                    params = event.get("params",{})
                    safe["params"] = {key:(safe_url(value) if key=="url" else value)
                                      for key,value in params.items() if key in {"url","timeout","waitUntil"}
                                      and isinstance(value,(str,int,float))}
                if isinstance(event.get("error"),dict):
                    safe["error"] = {"message":redact(event["error"].get("message",""))}
                encoded = json.dumps(safe,separators=(",",":")).encode()+b"\n"
                total += len(encoded)
                if total > limit:
                    raise EvidenceLimit("Sanitized trace exceeds artifact budget")
                lines.append(encoded)
            outgoing.writestr(Path(entry.filename).name,b"".join(lines))
        outgoing.writestr("trace.network",b"")


class Artifacts:
    def __init__(self, directory, result):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.result = result

    def disk_bytes(self):
        return sum(p.stat().st_size for p in self.directory.rglob("*") if p.is_file() and not p.is_symlink())

    def check_budget(self):
        if self.disk_bytes() > self.result.limits.max_evidence_bytes:
            raise EvidenceLimit("Discovery evidence budget reached")

    def register(self, name, kind, page_url=None):
        path = self.directory / name
        data = path.read_bytes()
        if len(data) > self.result.limits.max_artifact_bytes:
            path.unlink()
            raise EvidenceLimit(f"{kind} exceeds artifact budget")
        self.check_budget()
        item = Artifact(kind=kind,filename=name,page_url=page_url,size_bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),media_type={".png":"image/png",".zip":"application/zip",".json":"application/json"}[path.suffix])
        self.result.artifacts.append(item)
        return item

    def checkpoint(self):
        data = self.result.model_dump_json(indent=2)
        if len(data.encode()) > self.result.limits.max_artifact_bytes:
            raise EvidenceLimit("Application map exceeds artifact budget")
        temp = self.directory / "result.tmp"
        temp.write_text(data,encoding="utf-8")
        temp.replace(self.directory / "result.json")

    async def screenshot(self, page, record, index):
        name = "homepage.png" if index == 0 else f"page-{index:03d}.png"
        # Mask form values, iframes and explicitly private regions. No full-page images.
        await page.screenshot(path=str(self.directory/name),full_page=False,animations="disabled",
                              mask=[page.locator("input,textarea,select,iframe,[data-private]")],
                              timeout=self.result.limits.action_timeout*1000)
        self.register(name,"screenshot",record.url)
        record.screenshot = name

    def observations(self):
        for name,kind,items in (
            ("console.json","console",[o for o in self.result.observations if o.kind.startswith("console_")]),
            ("browser-errors.json","browser_error",[o for o in self.result.observations if not o.kind.startswith("console_")]),
            ("network.json","network",self.result.requests),
        ):
            (self.directory/name).write_text(json.dumps([i.model_dump(mode="json") for i in items],indent=2),encoding="utf-8")
            self.register(name,kind)
