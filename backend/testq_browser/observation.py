"""Bounded metadata-only observation. Headers, bodies and cookies are never read."""
import time
from urllib.parse import urlsplit
from .schemas import NetworkRequest, Observation, APIEndpoint
from .policies import same_origin, safe_url, redact


class Observer:
    def __init__(self, result):
        self.result = result
        self.page_url = result.base_url + "/"
        self.pending = {}

    def observe(self, kind, message, page_url=None):
        if len(self.result.observations) >= self.result.limits.max_observations:
            self.result.truncated = True
            return
        self.result.observations.append(Observation(
            run_id=self.result.run_id, session_id=self.result.session_id,
            page_url=safe_url(page_url or self.page_url), kind=kind, message=redact(message)))

    def request(self, request):
        if len(self.result.requests) >= self.result.limits.max_requests:
            self.result.truncated = True
            return
        url = safe_url(request.url)
        record = NetworkRequest(page_url=self.page_url, method=request.method, url=url,
                                path=urlsplit(url).path, resource_type=request.resource_type,
                                internal=same_origin(request.url,self.result.base_url))
        self.result.requests.append(record)
        self.pending[request] = (record,time.monotonic())

    def response(self, response):
        data = self.pending.get(response.request)
        if data:
            data[0].status = response.status

    def finished(self, request):
        data = self.pending.pop(request,None)
        if data:
            data[0].duration_ms = round((time.monotonic()-data[1])*1000,2)

    def failed(self, request):
        data = self.pending.get(request)
        if data:
            data[0].failure = redact(request.failure or "Request failed")
        self.observe("request_failed", f"{request.method} {safe_url(request.url)}: {redact(request.failure or '')}")
        self.finished(request)

    def console(self, message):
        kind = {"warning":"console_warn","error":"console_error","debug":"console_debug","info":"console_info"}.get(message.type,"console_log")
        self.observe(kind,message.text)

    def attach(self, page):
        page.on("console",self.console)
        page.on("pageerror",lambda error:self.observe("browser_error",str(error)))
        page.on("crash",lambda:self.observe("browser_crash","Chromium page crashed"))
        page.on("request",self.request)
        page.on("response",self.response)
        page.on("requestfinished",self.finished)
        page.on("requestfailed",self.failed)

    def endpoints(self):
        endpoints = {}
        for item in self.result.requests:
            if item.internal and (item.resource_type in ("xhr","fetch") or item.path.startswith("/api/")):
                endpoint = endpoints.setdefault((item.method,item.path),APIEndpoint(method=item.method,path=item.path))
                if item.status and item.status not in endpoint.statuses:
                    endpoint.statuses.append(item.status)
        self.result.api_endpoints = list(endpoints.values())
