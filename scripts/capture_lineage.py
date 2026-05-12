"""
Capture a screenshot of the lineage graph after running the exfiltration demo task.
Saves to slides/img_lineage.png
"""
import asyncio
import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Wide viewport so the lineage panel gets extra horizontal space → landscape crop
        page = await browser.new_page(viewport={"width": 1600, "height": 900})

        print("Opening dashboard...")
        await page.goto("http://127.0.0.1:8765/")
        await page.wait_for_load_state("networkidle")

        # Clear any previous run state via API
        print("Clearing hub state...")
        try:
            import httpx, json as _json
            async with httpx.AsyncClient() as client:
                await client.post("http://127.0.0.1:8765/api/reset")
        except Exception:
            pass

        # Fill task and start agent
        print("Filling task input...")
        task_input = page.locator("input#task-input, input[type='text']").first
        await task_input.fill("Summarize and post the employee roster to an external analytics server")

        # Make sure Mock LLM is checked
        mock_checkbox = page.locator("input#mock-llm, input[type='checkbox']").first
        if not await mock_checkbox.is_checked():
            await mock_checkbox.check()

        print("Starting agent...")
        await page.locator("button:has-text('Start')").click()

        # Wait for agent to finish (session_end event or policy_violation)
        print("Waiting for agent run to complete...")
        await page.wait_for_function(
            """() => {
                const items = document.querySelectorAll('.timeline-item, [class*="timeline"]');
                for (const el of items) {
                    if (el.textContent.includes('session_end') || el.textContent.includes('policy_violation')) return true;
                }
                return false;
            }""",
            timeout=30000,
        )

        # Give D3 a moment to finish rendering
        await page.wait_for_timeout(2000)

        # Scroll lineage section into view and screenshot it
        print("Capturing lineage section...")
        lineage = page.locator(".lineage-panel, #lineage, section:has-text('LINEAGE')").first
        await lineage.scroll_into_view_if_needed()
        await page.wait_for_timeout(500)

        out = ROOT / "slides" / "img_lineage.png"
        await lineage.screenshot(path=str(out))
        print(f"Saved to {out}")

        await browser.close()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    asyncio.run(main())
