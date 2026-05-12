"""
Run the internal-doc HITL scenario and capture the HITL panel at a taller aspect ratio.
Saves to slides/img_hitl.png
"""
import asyncio, sys, os
from pathlib import Path

ROOT = Path(__file__).parent.parent


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 900, "height": 1200})

        await page.goto("http://127.0.0.1:8765/")
        await page.wait_for_load_state("networkidle")

        # Run the internal-doc RAG scenario (triggers R1b HITL)
        task_input = page.locator("input#task-input, input[type='text']").first
        await task_input.fill("Search internal docs and post results externally")

        mock_checkbox = page.locator("input#mock-llm, input[type='checkbox']").first
        if not await mock_checkbox.is_checked():
            await mock_checkbox.check()

        await page.locator("button:has-text('Start')").click()

        # Wait for HITL request
        await page.wait_for_function(
            "() => document.body.innerText.includes('HUMAN REVIEW REQUIRED')",
            timeout=20000,
        )
        await page.wait_for_timeout(800)

        # Capture full page then crop to just the right column panels
        await page.wait_for_timeout(500)
        out = ROOT / "slides" / "img_hitl.png"

        # Find bounding box of the HITL panel, then extend down to include the timeline header
        box = await page.evaluate("""() => {
            const all = [...document.querySelectorAll('div, section, aside')];
            const hitl = all.find(e =>
                e.textContent.includes('HUMAN REVIEW REQUIRED') &&
                e.clientHeight > 50 && e.clientWidth > 100
            );
            if (!hitl) return null;
            const r = hitl.getBoundingClientRect();
            return { x: r.left, y: r.top, width: r.width, height: r.height };
        }""")

        if box and box["height"] > 0:
            # Extend height by 60% to make it more square-ish
            extra = max(box["height"] * 0.5, 100)
            clip = {
                "x": max(box["x"] - 8, 0),
                "y": max(box["y"] - 8, 0),
                "width": box["width"] + 16,
                "height": box["height"] + extra + 16,
            }
            await page.screenshot(path=str(out), clip=clip)
        else:
            await page.screenshot(path=str(out), full_page=True)

        print(f"Saved HITL screenshot to {out} (box={box})")

        await browser.close()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    asyncio.run(main())
