import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ARTIFACT_DIR = Path(r"C:\Users\owais\.gemini\antigravity-ide\brain\d5470c5a-187a-41fe-a4fd-e6e0730141e4")
BASE_URL = "http://localhost:3000"

PAGES = [
    ("landing_page", f"{BASE_URL}/"),
    ("runs_page", f"{BASE_URL}/runs"),
    ("overview_page", f"{BASE_URL}/run/demo-run-juice-shop/overview"),
    ("command_center_page", f"{BASE_URL}/run/demo-run-juice-shop/command-center"),
    ("application_map_page", f"{BASE_URL}/run/demo-run-juice-shop/application-map"),
    ("ai_strategy_page", f"{BASE_URL}/run/demo-run-juice-shop/ai-strategy"),
    ("tests_page", f"{BASE_URL}/run/demo-run-juice-shop/tests"),
    ("findings_page", f"{BASE_URL}/run/demo-run-juice-shop/findings"),
    ("evidence_page", f"{BASE_URL}/run/demo-run-juice-shop/evidence"),
    ("logs_page", f"{BASE_URL}/run/demo-run-juice-shop/logs"),
]

async def run_qa():
    console_errors = []
    page_results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.5,
        )
        page = await context.new_page()

        # Listen to console & responses
        def on_console(msg):
            if msg.type in ["error"]:
                console_errors.append(f"[{msg.type.upper()}] {msg.text}")
        page.on("console", on_console)

        def on_response(res):
            if res.status >= 400:
                print(f"  [HTTP {res.status}] Failed URL: {res.url}")
        page.on("response", on_response)

        # Set sessionStorage flag so boot sequence doesn't block page navigation after first run
        await page.goto(f"{BASE_URL}/")
        await page.evaluate("sessionStorage.setItem('testq_boot_seen', 'true')")

        for name, url in PAGES:
            print(f"Testing {name} -> {url}...")
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                status = response.status if response else 0
                await asyncio.sleep(2.0)  # Allow micro-animations and Three.js canvas to settle

                # Special interactions per page
                if name == "landing_page":
                    # Capture Hero screenshot first
                    hero_path = ARTIFACT_DIR / "qa_hero_sculpture.png"
                    await page.screenshot(path=str(hero_path), clip={"x": 0, "y": 0, "width": 1440, "height": 900})

                    # Scroll through the landing page to trigger R3F crack propagation and 4-phase diagrams
                    for y in [400, 900, 1600, 2400, 3200, 4000, 0]:
                        await page.evaluate(f"window.scrollTo(0, {y})")
                        await asyncio.sleep(0.3)
                    await asyncio.sleep(0.8)

                    # Capture Thesis section
                    thesis_el = page.locator("#thesis")
                    if await thesis_el.count() > 0:
                        await thesis_el.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        thesis_path = ARTIFACT_DIR / "qa_thesis_section.png"
                        await thesis_el.screenshot(path=str(thesis_path))
                        print(f"  [OK] Captured {thesis_path.name}")
                    await page.evaluate("window.scrollTo(0, 0)")

                elif name == "application_map_page":
                    # Click second route in list
                    catalog_button = page.locator("button:has-text('/catalog')")
                    if await catalog_button.count() > 0:
                        await catalog_button.first.click()
                        await asyncio.sleep(0.5)

                elif name == "ai_strategy_page":
                    # Click validation filter pill
                    val_btn = page.locator("button:has-text('VALIDATION')")
                    if await val_btn.count() > 0:
                        await val_btn.first.click()
                        await asyncio.sleep(0.3)
                        # Switch back to ALL
                        all_btn = page.locator("button:has-text('ALL')")
                        if await all_btn.count() > 0:
                            await all_btn.first.click()
                            await asyncio.sleep(0.3)

                elif name == "tests_page":
                    # Click to expand second test case if available
                    test_buttons = page.locator("button:has-text('NAV-001')")
                    if await test_buttons.count() > 0:
                        await test_buttons.first.click()
                        await asyncio.sleep(0.5)

                elif name == "evidence_page":
                    # Click thumbnail to verify modal
                    inspect_btn = page.locator("div[class*='cursor-pointer']").first
                    if await inspect_btn.count() > 0:
                        await inspect_btn.click()
                        await asyncio.sleep(0.5)
                        # Close modal
                        close_btn = page.locator("button:has-text('Close')")
                        if await close_btn.count() > 0:
                            await close_btn.click()
                            await asyncio.sleep(0.3)

                # Capture screenshot
                screenshot_path = ARTIFACT_DIR / f"qa_{name}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                page_results[name] = {
                    "status": status,
                    "screenshot": str(screenshot_path),
                    "ok": status == 200,
                }
                print(f"  [OK] {name} [HTTP {status}] -> Saved {screenshot_path.name}")
            except Exception as e:
                print(f"  [FAIL] {name} failed: {e}")
                page_results[name] = {"status": "ERROR", "error": str(e), "ok": False}

        await browser.close()

    print("\n--- QA REPORT SUMMARY ---")
    all_ok = all(r.get("ok", False) for r in page_results.values())
    print(f"All Pages Status: {'PASS' if all_ok else 'FAIL'}")
    print(f"Total Pages Checked: {len(page_results)}")
    print(f"Console Errors: {len(console_errors)}")
    for err in console_errors[:10]:
        print(f"  - {err}")

    return page_results, console_errors

if __name__ == "__main__":
    asyncio.run(run_qa())
