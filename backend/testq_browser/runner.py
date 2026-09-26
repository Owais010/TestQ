"""Deterministic bounded BFS. Runs only in the TestQ sandbox browser environment."""
import asyncio
import base64
import json
import sys
from pathlib import Path

from playwright.async_api import Error, TimeoutError as NavigationTimeout
from .schemas import DiscoveryRequest, ApplicationMap, PageRecord, now
from .policies import Frontier, redact, safe_url, same_origin
from .inspection import inspect_page
from .observation import Observer
from .artifacts import Artifacts, EvidenceLimit, sanitize_trace
from .browser import BrowserSession


class DiscoveryEngine:
    def __init__(self, request, output, browser_factory=BrowserSession):
        self.request = request
        self.result = ApplicationMap(run_id=request.run_id,session_id=request.session_id,
                                     base_url=request.base_url,limits=request.limits)
        self.observer = Observer(self.result)
        self.artifacts = Artifacts(output,self.result)
        self.browser = browser_factory(request,Path(output),self.observer)
        self.frontier = Frontier(request.base_url,request.limits.max_pages,request.limits.max_depth)

    async def visit(self, context, url, depth):
        record = PageRecord(url=safe_url(url),depth=depth)
        self.result.pages.append(record)
        self.observer.page_url = record.url
        index = len(self.result.pages)-1
        page = await context.new_page()
        self.observer.attach(page)
        page.on("dialog",lambda dialog:dialog.dismiss())
        page.on("popup",lambda popup:popup.close())
        tracing = self.request.limits.trace_enabled
        if tracing:
            await context.tracing.start(screenshots=False,snapshots=False,sources=False)
        try:
            response = await page.goto(url,wait_until="domcontentloaded")
            record.status = response.status if response else None
            record.final_url = safe_url(page.url)
            if not same_origin(page.url,self.request.base_url):
                raise Error("Navigation left the target application")
            record.navigation = "http_error" if record.status and record.status >= 400 else "ok"
            if record.navigation == "http_error":
                self.observer.observe("navigation_error",f"Observed HTTP {record.status}")
            # Small bounded observation window for initial client-side requests.
            await page.wait_for_timeout(min(250,self.request.limits.action_timeout*1000))
        except NavigationTimeout as error:
            record.navigation = "timeout"
            record.final_url = safe_url(page.url)
            self.observer.observe("navigation_error",f"Navigation timeout: {error}")
        except Error as error:
            record.navigation = "failed"
            record.final_url = safe_url(page.url)
            self.observer.observe("navigation_error",str(error))
        try:
            if same_origin(page.url,self.request.base_url) and not page.is_closed():
                links = await inspect_page(page,record,self.request.base_url,self.request.limits.max_elements)
                for item in links:
                    self.frontier.add(item["href"],depth+1,page.url)
            if not page.is_closed():
                await self.artifacts.screenshot(page,record,index)
        except Error as error:
            self.observer.observe("evidence_error",str(error))
        finally:
            try:
                if tracing:
                    raw = self.artifacts.directory/f"raw-{index:03d}.zip"
                    await asyncio.wait_for(context.tracing.stop(path=str(raw)),self.request.limits.action_timeout)
                    name = f"trace-{index:03d}.zip"
                    sanitize_trace(raw,self.artifacts.directory/name,self.request.limits.max_artifact_bytes)
                    raw.unlink(missing_ok=True)
                    self.artifacts.register(name,"trace",record.url)
            except (Error,TimeoutError,ValueError) as error:
                self.observer.observe("evidence_error",f"Trace unavailable: {error}")
            finally:
                await page.close()
        if not self.browser.browser.is_connected():
            raise Error("Browser disconnected")
        self.observer.endpoints()
        self.artifacts.checkpoint()

    async def crawl(self):
        context = await self.browser.open()
        while self.frontier.queue:
            url,depth = self.frontier.queue.popleft()
            await self.visit(context,url,depth)
        self.result.truncated |= self.frontier.limited
        if self.frontier.limited:
            self.observer.observe("limit_reached","Page/depth frontier limit reached")

    async def watch_budget(self):
        while True:
            self.artifacts.check_budget()
            await asyncio.sleep(0.1)

    async def run(self):
        self.artifacts.checkpoint()
        tasks = []
        try:
            async with asyncio.timeout(self.request.limits.discovery_timeout):
                tasks = [asyncio.create_task(self.crawl()),asyncio.create_task(self.watch_budget())]
                done,_ = await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
                self.result.status = "completed"
        except TimeoutError:
            self.result.status = "timed_out"
            self.result.error = "Discovery deadline exceeded"
            self.observer.observe("discovery_timeout",self.result.error)
        except EvidenceLimit as error:
            self.result.status = "failed"
            self.result.truncated = True
            self.result.error = str(error)
            self.observer.observe("limit_reached",str(error))
        except Exception as error:
            self.result.status = "failed"
            self.result.error = redact(str(error))
            self.observer.observe("browser_crash",self.result.error)
        finally:
            for task in tasks:
                if not task.done(): task.cancel()
            if tasks:
                await asyncio.gather(*tasks,return_exceptions=True)
            try:
                await asyncio.wait_for(self.browser.close(),5)
            except Exception as error:
                self.observer.observe("browser_crash",f"Browser close: {error}")
            self.observer.endpoints()
            self.result.finished_at = now()
            for record in self.result.pages:
                if record.navigation == "pending":
                    record.navigation = "timeout" if self.result.status == "timed_out" else "failed"
            try:
                self.artifacts.observations()
            except EvidenceLimit as error:
                self.result.status = "failed"
                self.result.error = str(error)
            self.artifacts.checkpoint()
        return self.result


def main():
    request = DiscoveryRequest.model_validate_json(base64.b64decode(sys.argv[1],validate=True))
    output = Path("/discovery")/request.session_id
    result = asyncio.run(DiscoveryEngine(request,output).run())
    print(json.dumps({"session_id":result.session_id,"status":result.status,"pages":len(result.pages)}))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
