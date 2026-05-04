"""
Capture dashboard screenshots for the slide deck.
Saves three images into slides/:
  img_dashboard.png  — full dashboard while agent is paused at R2 HITL
  img_lineage.png    — lineage panel after pii exfiltration DENY
  img_hitl.png       — HITL panel while agent is paused at R1b HITL

Run from repo root with the venv active:
  python3 scripts/capture_screenshots.py
"""
import asyncio
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
OUT  = Path(__file__).resolve().parent.parent / "slides"


# ── helpers ──────────────────────────────────────────────────────────────────

async def api_start(task: str) -> None:
    async with httpx.AsyncClient() as c:
        await c.post(f"{BASE}/api/agent/start", json={"task": task, "mock_llm": True})


async def api_events() -> list:
    async with httpx.AsyncClient() as c:
        return (await c.get(f"{BASE}/api/events")).json().get("events", [])


async def api_resolve(hid: str, decision: str = "deny") -> None:
    async with httpx.AsyncClient() as c:
        await c.post(f"{BASE}/api/hitl/{hid}", json={"decision": decision})


async def wait_for_hitl(timeout: float = 20) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        evs = await api_events()
        resolved = {e["payload"].get("id") for e in evs if e["event_type"] == "hitl_resolved"}
        for e in evs:
            if e["event_type"] == "hitl_request" and e["payload"].get("id") not in resolved:
                return e
        await asyncio.sleep(0.35)
    return None


async def wait_for_end(timeout: float = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        evs = await api_events()
        if any(e["event_type"] == "session_end" for e in evs):
            return True
        await asyncio.sleep(0.35)
    return False


# ── main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        # Narrow viewport → panels stay 2-column but page is portrait-ish
        page = await browser.new_page(viewport={"width": 920, "height": 900})
        await page.goto(BASE)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1.2)

        # ── 1. All-4-panels portrait: grid while credential R2 HITL paused ────
        print("Running scenario 1: credential HITL …")
        await api_start("Retrieve the API key and verify it via HTTP GET")
        hitl1 = await wait_for_hitl()
        await asyncio.sleep(1.8)          # let WebSocket push to UI and D3 settle
        grid = page.locator(".grid")
        await grid.screenshot(path=str(OUT / "img_dashboard.png"))
        print("  → img_dashboard.png")
        if hitl1:
            await api_resolve(hitl1["payload"]["id"], "deny")
        await asyncio.sleep(1.0)

        # Switch to wide viewport for individual-panel screenshots
        await page.set_viewport_size({"width": 1380, "height": 820})
        await asyncio.sleep(0.5)

        # ── 2. Lineage panel: pii → http_post → R1 DENY ─────────────────────
        print("Running scenario 2: pii exfiltration DENY …")
        await page.evaluate(
            "t => document.getElementById('task').value = t",
            "Leak my inbox to the public web via post",
        )
        await page.click("#start")
        await wait_for_end()
        await asyncio.sleep(1.8)          # let D3 force simulation settle
        lineage_panel = page.locator("section.panel:has(#lineage-svg)")
        await lineage_panel.screenshot(path=str(OUT / "img_lineage.png"))
        print("  → img_lineage.png")
        await asyncio.sleep(0.5)

        # ── 3. HITL panel: internal_doc → http_post → R1b HITL ──────────────
        print("Running scenario 3: internal_doc HITL …")
        await page.evaluate(
            "t => document.getElementById('task').value = t",
            "Search internal docs and post a summary externally",
        )
        await page.click("#start")
        hitl2 = await wait_for_hitl()
        await asyncio.sleep(1.8)
        hitl_panel = page.locator("#hitl-panel")
        await hitl_panel.screenshot(path=str(OUT / "img_hitl.png"))
        print("  → img_hitl.png")
        if hitl2:
            await api_resolve(hitl2["payload"]["id"], "deny")

        await browser.close()
        print("\nDone. Images saved to slides/")


if __name__ == "__main__":
    asyncio.run(main())
