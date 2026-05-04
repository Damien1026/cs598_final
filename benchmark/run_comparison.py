"""
LLM Comparison Benchmark — CS598 Final Project

Runs 3 email tasks on Gemini 2.5 Flash and DeepSeek, records latency/tokens/output,
then generates an HTML comparison report.

Usage:
    python3 -m benchmark.run_comparison            # mock emails
    python3 -m benchmark.run_comparison --email    # real 163 IMAP
    python3 -m benchmark.run_comparison --models gemini:gemini-2.5-flash deepseek:deepseek-chat
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Mock email corpus (used when --email is not passed)
# ---------------------------------------------------------------------------

MOCK_EMAILS = """\
Inbox (6 messages):

(1) From: Prof. Johnson <prof.johnson@university.edu>
    Subject: CS598 Final Project Deadline Extended
    Date: Mon, 28 Apr 2026 09:00:00 -0500
    Body: Good news — the final project submission deadline has been extended to May 10. Please make sure your GitHub repo is updated and your demo video is uploaded by then. Let me know if you have questions.

(2) From: Alice Chen <alice.chen@teamlab.com>
    Subject: Re: Sprint Review Tomorrow
    Date: Mon, 28 Apr 2026 10:30:00 -0500
    Body: Confirmed — I'll prepare the demo slides by 2pm. Can you send me the updated metrics from last week's run? We need them for the stakeholder section.

(3) From: noreply@amazon.com <noreply@amazon.com>
    Subject: Your order #112-3456789 has shipped
    Date: Mon, 28 Apr 2026 11:00:00 -0500
    Body: Your order containing "USB-C Hub 7-in-1" has shipped and will arrive by Wednesday. Track your package at the link below.

(4) From: HR Department <hr@company.com>
    Subject: URGENT: Benefits Enrollment Closes Friday
    Date: Tue, 29 Apr 2026 08:00:00 -0500
    Body: This is a reminder that open enrollment for 2026 health benefits closes this Friday April 30 at 5pm. If you do not enroll, you will be defaulted to the basic plan. Log in to the HR portal to make your selections.

(5) From: Bob Martinez <bob.martinez@partner.org>
    Subject: Partnership Proposal — Q3 Integration
    Date: Tue, 29 Apr 2026 14:00:00 -0500
    Body: Hi, following up on our call last week. I've attached the draft partnership proposal for Q3. We'd like a response by May 5 so we can align timelines with our board meeting. Please review and let me know your thoughts.

(6) From: newsletter@techdigest.io <newsletter@techdigest.io>
    Subject: This week in AI: GPT-5, Gemini 3, and more
    Date: Wed, 30 Apr 2026 07:00:00 -0500
    Body: Top stories this week: OpenAI releases GPT-5 with 2M token context; Google announces Gemini 3 with multimodal reasoning; Meta open-sources a new 70B model. Click to read the full digest.
"""

# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

TASKS: list[dict[str, str]] = [
    {
        "id": "summarize",
        "name": "Inbox Summary",
        "prompt_template": (
            "You are an intelligent email assistant.\n\n"
            "Here is the user's inbox:\n{emails}\n\n"
            "Please summarize the inbox in 3–5 concise bullet points, "
            "highlighting the most important topics."
        ),
    },
    {
        "id": "extract",
        "name": "Structured Extraction",
        "prompt_template": (
            "You are an intelligent email assistant.\n\n"
            "Here is the user's inbox:\n{emails}\n\n"
            "Extract the following fields from each email and output a JSON array. "
            "Each element must have: sender, subject, date, urgency_level (low/medium/high), "
            "action_required (true/false). Output ONLY the JSON array, no prose."
        ),
    },
    {
        "id": "prioritize",
        "name": "Priority & Action Decision",
        "prompt_template": (
            "You are an intelligent email assistant.\n\n"
            "Here is the user's inbox:\n{emails}\n\n"
            "Sort the emails by importance (1 = most important). For each email output:\n"
            "- rank (int)\n"
            "- subject (str)\n"
            "- reason (one sentence why this rank)\n"
            "- action_needed (true/false)\n"
            "- suggestion (brief, ≤15 words, or null)\n\n"
            "Output as a JSON array only."
        ),
    },
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    model: str
    task_id: str
    task_name: str
    latency_s: float
    tokens: int
    output: str
    error: str = ""


@dataclass
class BenchmarkRun:
    timestamp: str
    models: list[str]
    email_source: str
    results: list[TaskResult] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

async def _call_llm(llm: Any, prompt: str) -> tuple[str, int]:
    """Single LLM call; returns (output_text, token_count)."""
    from agent.llm import GeminiLLM

    if isinstance(llm, GeminiLLM):
        messages = [{"role": "user", "parts": [prompt]}]
    else:
        messages = [{"role": "user", "content": prompt}]

    resp = await llm.chat(messages, tools=None)
    return resp.get("content", ""), resp.get("tokens", getattr(llm, "last_token_count", 0))


async def run_task(llm: Any, model_label: str, task: dict[str, str], emails: str) -> TaskResult:
    prompt = task["prompt_template"].format(emails=emails)
    print(f"  [{model_label}] {task['name']} ...", end="", flush=True)
    t0 = time.perf_counter()
    try:
        output, tokens = await _call_llm(llm, prompt)
        latency = round(time.perf_counter() - t0, 2)
        print(f" {latency}s, {tokens} tok")
        return TaskResult(
            model=model_label,
            task_id=task["id"],
            task_name=task["name"],
            latency_s=latency,
            tokens=tokens,
            output=output,
        )
    except Exception as exc:
        latency = round(time.perf_counter() - t0, 2)
        print(f" ERROR: {exc}")
        return TaskResult(
            model=model_label,
            task_id=task["id"],
            task_name=task["name"],
            latency_s=latency,
            tokens=0,
            output="",
            error=str(exc),
        )


async def run_benchmark(model_specs: list[str], emails: str, email_source_label: str) -> BenchmarkRun:
    from agent.llm import make_llm

    run = BenchmarkRun(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        models=model_specs,
        email_source=email_source_label,
    )

    for spec in model_specs:
        llm = make_llm(spec)
        print(f"\n=== {spec} ===")
        for task in TASKS:
            result = await run_task(llm, spec, task, emails)
            run.results.append(result)
            # Small pause between calls to avoid rate limits
            await asyncio.sleep(1.0)

    return run

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="LLM comparison benchmark")
    p.add_argument("--email", action="store_true", help="Fetch real inbox via 163 IMAP")
    p.add_argument(
        "--models",
        nargs="+",
        default=["gemini:gemini-2.5-flash", "deepseek:deepseek-chat"],
        help="LLM specs to compare (default: gemini:gemini-2.5-flash deepseek:deepseek-chat)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("benchmark/results"),
        help="Output directory for JSON + HTML (default: benchmark/results)",
    )
    args = p.parse_args()

    # Load .env
    env_file = Path(".env")
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    # Fetch emails
    if args.email:
        from agent.sources.email import EmailSource
        print("Fetching inbox via IMAP...")
        emails = EmailSource().fetch()
        email_source_label = "163 IMAP"
    else:
        emails = MOCK_EMAILS
        email_source_label = "mock"

    print(f"\nEmail source: {email_source_label}")
    print(f"Models: {', '.join(args.models)}")
    print(f"Tasks: {len(TASKS)}\n")

    run = asyncio.run(run_benchmark(args.models, emails, email_source_label))

    # Save JSON
    args.out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = args.out / f"comparison_{ts}.json"
    json_path.write_text(
        json.dumps(
            {
                "timestamp": run.timestamp,
                "models": run.models,
                "email_source": run.email_source,
                "results": [asdict(r) for r in run.results],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nResults saved → {json_path}")

    # Generate HTML report
    from benchmark.report import generate_report
    html_path = args.out / f"comparison_{ts}.html"
    generate_report(run, html_path)
    print(f"Report saved  → {html_path}")


if __name__ == "__main__":
    main()
