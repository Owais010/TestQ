"""Chromium lifecycle and same-origin request enforcement."""
from playwright.async_api import async_playwright
from .policies import same_origin, safe_url


class BrowserSession:
    def __init__(self, request, directory, observer):
        self.request, self.directory, self.observer = request,directory,observer
        self.driver = self.browser = self.context = None

    async def open(self):
        self.driver = await async_playwright().start()
        self.browser = await self.driver.chromium.launch(
            headless=True, chromium_sandbox=True,
            traces_dir=str(self.directory/"raw"),
            timeout=self.request.limits.navigation_timeout*1000,
            args=["--disable-background-networking","--disable-component-update","--disable-sync"],
        )
        self.context = await self.browser.new_context(
            viewport={"width":1280,"height":720},device_scale_factor=1,
            locale="en-US",timezone_id="UTC",reduced_motion="reduce",
            service_workers="block",accept_downloads=False,permissions=[],
        )
        self.context.set_default_navigation_timeout(self.request.limits.navigation_timeout*1000)
        self.context.set_default_timeout(self.request.limits.action_timeout*1000)
        await self.context.route("**/*",self.route)
        await self.context.route_web_socket("**/*",lambda socket: socket.close())
        return self.context

    async def route(self, route):
        if same_origin(route.request.url,self.request.base_url):
            await route.continue_()
        else:
            self.observer.observe("external_blocked",f"Blocked {safe_url(route.request.url)}")
            await route.abort("blockedbyclient")

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        finally:
            if self.driver:
                await self.driver.stop()
