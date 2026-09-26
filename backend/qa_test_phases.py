import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def test_phases():
    artifact_dir = Path(r"C:\Users\owais\.gemini\antigravity-ide\brain\d5470c5a-187a-41fe-a4fd-e6e0730141e4")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:3000/")
        await asyncio.sleep(1.0)
        
        # Scroll to How It Works / FourPhaseProcess
        how_section = page.locator("#how-it-works")
        await how_section.scroll_into_view_if_needed()
        await asyncio.sleep(0.8)
        
        # Test clicking each phase tab
        for name in ["DISCOVER", "REASON", "BREAK", "PROVE"]:
            tab = page.locator(f"button:has-text('{name}')").first
            await tab.click()
            await asyncio.sleep(0.8)
            screenshot_path = artifact_dir / f"qa_phase_{name.lower()}.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"[OK] Captured {name} -> {screenshot_path.name}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_phases())
