from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_DASHBOARD_URL = os.environ.get("OBS_DASHBOARD_URL", "http://127.0.0.1:8765")


def _register_dashboard_forwarder(hub: "ObsHub") -> None:  # type: ignore[name-defined]
    """Subscribe a callback that forwards every event to the running dashboard server.
    Silently skips if the dashboard is not reachable."""
    import httpx

    async def _forward(event) -> None:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.post(
                    f"{_DASHBOARD_URL}/api/ingest",
                    json=event.model_dump(mode="json"),
                )
        except Exception:
            pass

    hub.bus.subscribe(_forward)


# ------------------------------------------------------------------ single-task mode (legacy)

async def _run_single(task: str, workspace: Path, mock_llm: bool) -> None:
    from observe.hub import ObsHub
    from agent.runner import build_agent

    log = workspace / "logs" / "events.jsonl"
    trust = workspace / "logs" / "trust.json"
    hub = ObsHub(jsonl_path=log, trust_path=trust)
    agent = build_agent(workspace, hub, mock_llm=mock_llm)
    out = await agent.run(task)
    print(out or "(no final message)")


# ------------------------------------------------------------------ cluster REPL mode

async def _run_cluster(
    workspace: Path,
    llm_spec: str,
    use_email: bool,
    rag_docs: Path | None,
) -> None:
    from observe.hub import ObsHub
    from agent.llm import make_llm
    from agent.agents.orchestrator import Orchestrator
    from agent.sources.email import EmailSource
    from agent.sources.rag import RAGSource

    # Load .env if present
    env_file = Path(".env")
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    log = workspace / "logs" / "events.jsonl"
    trust = workspace / "logs" / "trust.json"
    (workspace / "workspace" / "notes").mkdir(parents=True, exist_ok=True)
    (workspace / "workspace" / "reports").mkdir(parents=True, exist_ok=True)

    hub = ObsHub(jsonl_path=log, trust_path=trust)
    _register_dashboard_forwarder(hub)
    llm = make_llm(llm_spec)

    email_source = EmailSource() if use_email else None
    rag_source = RAGSource(rag_docs) if rag_docs and rag_docs.is_dir() else None

    orch = Orchestrator(
        llm,
        workspace,
        hub,
        email_source=email_source,
        rag_source=rag_source,
    )

    model_label = llm_spec
    print(f"\n  Agent cluster ready  |  LLM: {model_label}")
    print(f"  Email: {'163 IMAP' if email_source else 'mock'}")
    print(f"  RAG:   {str(rag_docs) if rag_source else 'mock'}")
    print("  Type 'exit' or Ctrl-C to quit, 'reset' to clear history.\n")

    while True:
        try:
            user_input = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("Bye.")
            break
        if user_input.lower() == "reset":
            orch.reset()
            print("(conversation history cleared)\n")
            continue

        print("ai  > ", end="", flush=True)
        try:
            async for chunk in orch.stream_turn(user_input):
                print(chunk, end="", flush=True)
        except Exception as exc:
            print(f"\n[error] {exc}")
        print("\n")


# ------------------------------------------------------------------ entry point

def main() -> None:
    p = argparse.ArgumentParser(description="CS598 observability agent")
    sub = p.add_subparsers(dest="mode")

    # Legacy single-task mode
    single = sub.add_parser("run", help="Run a single task (mock or Ollama)")
    single.add_argument("--task", required=True)
    single.add_argument("--workspace", type=Path, default=None)
    single.add_argument("--mock-llm", action="store_true")

    # Cluster REPL mode
    cluster = sub.add_parser("chat", help="Interactive multi-agent cluster (Gemini)")
    cluster.add_argument(
        "--llm",
        default="gemini:gemini-2.5-flash",
        help="LLM spec: gemini:<model> | ollama:<model>  (default: gemini:gemini-2.5-flash)",
    )
    cluster.add_argument("--email", action="store_true", help="Use real 163 email via IMAP")
    cluster.add_argument(
        "--rag-docs",
        type=Path,
        default=Path("rag_docs"),
        help="Directory of .md/.txt documents for RAG (default: ./rag_docs)",
    )
    cluster.add_argument("--workspace", type=Path, default=None)

    args = p.parse_args()

    if args.mode == "run" or args.mode is None:
        # Backwards-compatible: if no subcommand, treat as legacy run
        if args.mode is None:
            # Re-parse with legacy flags
            legacy = argparse.ArgumentParser()
            legacy.add_argument("--task", required=True)
            legacy.add_argument("--workspace", type=Path, default=None)
            legacy.add_argument("--mock-llm", action="store_true")
            args = legacy.parse_args()

        root = (args.workspace or Path(os.environ.get("OBS_WORKSPACE", "sandbox"))).resolve()
        root.mkdir(parents=True, exist_ok=True)
        (root / "workspace" / "notes").mkdir(parents=True, exist_ok=True)
        asyncio.run(_run_single(args.task, root, args.mock_llm))

    elif args.mode == "chat":
        root = (args.workspace or Path(os.environ.get("OBS_WORKSPACE", "sandbox"))).resolve()
        root.mkdir(parents=True, exist_ok=True)
        asyncio.run(
            _run_cluster(
                workspace=root,
                llm_spec=args.llm,
                use_email=args.email,
                rag_docs=args.rag_docs,
            )
        )


if __name__ == "__main__":
    main()
