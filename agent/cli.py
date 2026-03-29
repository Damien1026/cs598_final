from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from observe.hub import ObsHub
from agent.runner import build_agent


async def _run(task: str, workspace: Path, mock_llm: bool) -> None:
    log = workspace / "logs" / "events.jsonl"
    trust = workspace / "logs" / "trust.json"
    hub = ObsHub(jsonl_path=log, trust_path=trust)
    agent = build_agent(workspace, hub, mock_llm=mock_llm)
    out = await agent.run(task)
    print(out or "(no final message)")


def main() -> None:
    p = argparse.ArgumentParser(description="Run monitored local LLM agent (CLI)")
    p.add_argument("--task", type=str, required=True, help="User task / instruction")
    p.add_argument("--workspace", type=Path, default=None, help="Sandbox root (default: ./sandbox)")
    p.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM (no Ollama)")
    args = p.parse_args()
    root = (args.workspace or Path(os.environ.get("OBS_WORKSPACE", "sandbox"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "notes").mkdir(parents=True, exist_ok=True)
    asyncio.run(_run(args.task, root, args.mock_llm))


if __name__ == "__main__":
    main()
