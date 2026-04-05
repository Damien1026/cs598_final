"""Generate cs598_demo_guide.pdf — updated for Phase 2 multi-agent cluster."""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── palette ──────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1a2e4a")
TEAL   = colors.HexColor("#0d7377")
SLATE  = colors.HexColor("#3d5a80")
LIGHT  = colors.HexColor("#f0f4f8")
CODE_BG = colors.HexColor("#f5f5f5")
RED    = colors.HexColor("#c0392b")
GREEN  = colors.HexColor("#27ae60")
ORANGE = colors.HexColor("#e67e22")
GRAY   = colors.HexColor("#888888")

# ── styles ────────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()

def S(name, **kw):
    s = ParagraphStyle(name, parent=base["Normal"], **kw)
    return s

sTitle   = S("sTitle",   fontSize=28, textColor=NAVY,  leading=36, alignment=TA_CENTER, spaceAfter=6,  fontName="Helvetica-Bold")
sSubtitle= S("sSubtitle",fontSize=13, textColor=SLATE, leading=18, alignment=TA_CENTER, spaceAfter=4,  fontName="Helvetica")
sMeta    = S("sMeta",    fontSize=10, textColor=GRAY,  leading=14, alignment=TA_CENTER, spaceAfter=2,  fontName="Helvetica-Oblique")
sH1      = S("sH1",      fontSize=16, textColor=NAVY,  leading=22, spaceBefore=18, spaceAfter=6,  fontName="Helvetica-Bold")
sH2      = S("sH2",      fontSize=13, textColor=TEAL,  leading=18, spaceBefore=12, spaceAfter=4,  fontName="Helvetica-Bold")
sH3      = S("sH3",      fontSize=11, textColor=SLATE, leading=16, spaceBefore=8,  spaceAfter=3,  fontName="Helvetica-Bold")
sBody    = S("sBody",    fontSize=10, textColor=colors.HexColor("#222222"), leading=15, spaceAfter=6)
sBullet  = S("sBullet",  fontSize=10, textColor=colors.HexColor("#222222"), leading=15, spaceAfter=3, leftIndent=16, bulletIndent=4)
sCode    = S("sCode",    fontSize=8.5, fontName="Courier", leading=13, spaceAfter=2,
             backColor=CODE_BG, leftIndent=12, rightIndent=12, borderPad=6)
sNote    = S("sNote",    fontSize=9,  textColor=colors.HexColor("#555555"), leading=13,
             leftIndent=12, spaceAfter=6, fontName="Helvetica-Oblique")
sWarn    = S("sWarn",    fontSize=9,  textColor=RED,   leading=13, leftIndent=12, spaceAfter=6)

def h1(t): return [Spacer(1, 4), Paragraph(t, sH1), HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=6)]
def h2(t): return [Paragraph(t, sH2)]
def h3(t): return [Paragraph(t, sH3)]
def body(t): return [Paragraph(t, sBody)]
def bullet(items): return [Paragraph(f"• {i}", sBullet) for i in items]
def note(t): return [Paragraph(f"ℹ️  {t}", sNote)]
def warn(t): return [Paragraph(f"⚠  {t}", sWarn)]
def sp(n=6): return [Spacer(1, n)]
def code(lines): return [Paragraph(line.replace(" ", "&nbsp;").replace("<", "&lt;").replace(">", "&gt;"), sCode) for line in lines] + [Spacer(1, 4)]
def hr(): return [HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=4)]

def badge_table(items):
    """items: list of (label, color, text)"""
    data = [[Paragraph(f'<font color="white"><b>{label}</b></font>', ParagraphStyle("b", fontSize=8, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)),
             Paragraph(text, ParagraphStyle("bt", fontSize=9, leading=12))]
            for label, c, text in items]
    t = Table(data, colWidths=[1.1*inch, 5.2*inch])
    ts = TableStyle([("BACKGROUND", (0, i), (0, i), items[i][1]) for i in range(len(items))] +
                    [("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, LIGHT]),
                     ("TOPPADDING", (0, 0), (-1, -1), 4),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                     ("LEFTPADDING", (0, 0), (-1, -1), 6),
                     ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                     ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
    t.setStyle(ts)
    return [t, Spacer(1, 6)]

def ref_table(headers, rows, col_widths=None):
    data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle("th", fontSize=9, fontName="Helvetica-Bold")) for h in headers]] + \
           [[Paragraph(str(c), ParagraphStyle("td", fontSize=9, leading=12)) for c in row] for row in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [t, Spacer(1, 8)]


# ── page template ─────────────────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    w, h = letter
    # header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 28, w, 28, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.5*inch, h - 18, "CS598 Privacy & Security Observability for LLM Agents")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 0.5*inch, h - 18, "User Manual — Phase 2")
    # footer
    canvas.setFillColor(GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(w / 2, 20, f"Page {doc.page}")
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, w, 8, fill=1, stroke=0)
    canvas.restoreState()


# ── build content ─────────────────────────────────────────────────────────────
def build():
    out = Path("/Users/damien/Desktop/cs598_demo_guide.pdf")
    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        topMargin=0.7*inch,
        bottomMargin=0.55*inch,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
    )

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 1.0*inch),
        Paragraph("CS598", ParagraphStyle("cTag", fontSize=12, textColor=TEAL, alignment=TA_CENTER, fontName="Helvetica-Bold")),
        Spacer(1, 8),
        Paragraph("Privacy &amp; Security Observability", sTitle),
        Paragraph("for Local LLM Agents", sTitle),
        Spacer(1, 12),
        Paragraph("User Manual — Phase 2: Real Data &amp; Multi-Agent Cluster", sSubtitle),
        Spacer(1, 20),
        HRFlowable(width="60%", thickness=2, color=TEAL, hAlign="CENTER"),
        Spacer(1, 20),
        Paragraph("University of Illinois Urbana-Champaign", sMeta),
        Paragraph("Spring 2026 Final Project", sMeta),
        Spacer(1, 0.5*inch),
    ]

    # cover feature boxes
    cover_data = [
        [Paragraph("<b>Gemini 2.0 Flash</b>", ParagraphStyle("cb", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)),
         Paragraph("<b>163 IMAP Email</b>", ParagraphStyle("cb", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)),
         Paragraph("<b>BM25 RAG</b>", ParagraphStyle("cb", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)),
         Paragraph("<b>3-Agent Cluster</b>", ParagraphStyle("cb", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER))],
        [Paragraph("Real LLM via\nGoogle AI Studio API", ParagraphStyle("cs", fontSize=9, alignment=TA_CENTER, leading=13)),
         Paragraph("Live inbox via\nIMAP + Auth Code", ParagraphStyle("cs", fontSize=9, alignment=TA_CENTER, leading=13)),
         Paragraph("Local knowledge base\nzero model download", ParagraphStyle("cs", fontSize=9, alignment=TA_CENTER, leading=13)),
         Paragraph("Researcher + Analyst\n+ Output agents", ParagraphStyle("cs", fontSize=9, alignment=TA_CENTER, leading=13))],
    ]
    ct = Table(cover_data, colWidths=[1.6*inch]*4)
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), TEAL),
        ("BACKGROUND", (1, 0), (1, 0), SLATE),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#5c6bc0")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#00838f")),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [ct, PageBreak()]

    # ── 1. Overview ────────────────────────────────────────────────────────────
    story += h1("1. Project Overview")
    story += body(
        "This project wraps a tool-calling LLM agent in a full observability layer that tracks "
        "information flow, enforces privacy policies, computes risk scores, and — when necessary — "
        "pauses execution for human review. Phase 2 replaces all mock data sources with real "
        "integrations and introduces a streaming multi-agent cluster backed by Gemini."
    )
    story += sp()
    story += h2("1.1 What is New in Phase 2")
    story += bullet([
        "Gemini 2.0 Flash as the live LLM (replaces MockLLM / Ollama-only)",
        "Real email via 163 IMAP — reads your actual inbox",
        "BM25 full-text RAG over local Markdown documents (zero model download)",
        "Three-agent cluster: Researcher → Analyst → Output, coordinated by an Orchestrator",
        "Streaming multi-turn REPL — responses print token-by-token",
        "Context-usage monitoring with per-turn token tracking and 80 % threshold warnings",
        "agent_id injected into every observability event for agent-level filtering",
    ])
    story += sp()
    story += h2("1.2 Observability Pipeline (unchanged)")
    story += body(
        "Every I/O action — regardless of which agent performs it — flows through MonitoredIO, "
        "which applies the four-stage pipeline:"
    )
    story += badge_table([
        ("Taint",   TEAL,  "Labels data as public / internal_doc / pii / credential based on content heuristics and source."),
        ("Policy",  SLATE, "Hard rules: deny obvious leaks; HITL for ambiguous writes with sensitive labels."),
        ("Risk",    colors.HexColor("#e67e22"), "Numeric score = sensitivity×0.55 + sink×0.35 + depth×0.10 − trust_offset."),
        ("HITL",   RED,   "If risk ≥ threshold or policy says hitl, the agent suspends until a human approves or denies."),
    ])

    story += [PageBreak()]

    # ── 2. Architecture ────────────────────────────────────────────────────────
    story += h1("2. Architecture")
    story += h2("2.1 Multi-Agent Cluster")
    story += body(
        "The Orchestrator receives every user message, decides which specialist agents to invoke "
        "(via Gemini function calling), waits for their results, then streams the final answer "
        "back to the terminal."
    )
    story += sp(4)
    arch_data = [
        ["Layer", "Component", "Role"],
        ["User", "REPL (cli.py chat)", "Streams input / receives streamed output"],
        ["Orchestrator", "Gemini 2.0 Flash", "Task decomposition, agent delegation, final synthesis"],
        ["Researcher", "Gemini 2.0 Flash", "fetch_email · rag_search · http_get"],
        ["Analyst", "Gemini 2.0 Flash", "read_file · write_note (workspace/notes/)"],
        ["Output", "Gemini 2.0 Flash", "write_report (workspace/reports/) · http_post"],
        ["Observability", "MonitoredIO → ObsHub", "Taint · Policy · Risk · HITL · EventBus"],
        ["Dashboard", "FastAPI + WebSocket", "Real-time event stream at localhost:8765"],
    ]
    story += ref_table(
        ["Layer", "Component", "Role"],
        arch_data[1:],
        col_widths=[1.2*inch, 1.8*inch, 3.3*inch],
    )

    story += h2("2.2 Agent Tool Permissions")
    story += ref_table(
        ["Agent", "Allowed Tools", "Forbidden"],
        [
            ["Researcher", "fetch_email, rag_search, http_get", "All file/HTTP writes"],
            ["Analyst", "read_file, write_note", "External HTTP, reports"],
            ["Output", "write_report, http_post", "Email, RAG, file reads"],
            ["Orchestrator", "delegate_to_* (meta tools only)", "Direct I/O tools"],
        ],
        col_widths=[1.1*inch, 2.5*inch, 2.7*inch],
    )

    story += h2("2.3 Taint Label Reference")
    story += ref_table(
        ["Label", "Triggered by", "Example Sources"],
        [
            ["public",       "Default (no signal)",                          "public_faq.md, plain HTTP responses"],
            ["internal_doc", "Keywords: roadmap, legacy API, internal notes", "project_roadmap.md, company_policy.md"],
            ["pii",          "Email addresses, SSN pattern (\\d{3}-\\d{2}-\\d{4})", "employee_roster.md, inbox emails"],
            ["credential",   "sk-… key pattern, API_KEY substring",          "api_keys.md, RAG chunks with secrets"],
        ],
        col_widths=[1.1*inch, 2.5*inch, 2.7*inch],
    )

    story += h2("2.4 Policy Rules")
    story += ref_table(
        ["Rule", "Condition", "Action"],
        [
            ["R1",  "pii or credential → http_post_external",        "DENY"],
            ["R1b", "internal_doc → http_post_external",             "HITL"],
            ["R2",  "credential → http_get_external",                "HITL"],
            ["R3",  "internal_doc/pii/credential → file outside allowlist", "DENY"],
            ["R4",  "pii → file write inside allowlist",             "HITL"],
        ],
        col_widths=[0.6*inch, 3.4*inch, 1.6*inch],
    )
    story += note("Allowlisted write paths: workspace/, notes/, ./")

    story += [PageBreak()]

    # ── 3. Setup ───────────────────────────────────────────────────────────────
    story += h1("3. Setup")
    story += h2("3.1 Prerequisites")
    story += bullet([
        "Python 3.11+",
        "Git (project already cloned)",
        "Internet access for Gemini API calls",
        "163 email account with IMAP enabled (optional but recommended)",
    ])

    story += h2("3.2 Install Dependencies")
    story += code([
        "cd ~/PycharmProjects/cs598_final",
        "python3 -m venv .venv",
        "source .venv/bin/activate",
        "pip install -r requirements.txt",
    ])
    story += body("Key new packages added in Phase 2:")
    story += ref_table(
        ["Package", "Purpose"],
        [
            ["google-generativeai >= 0.8", "Gemini API: chat, function calling, streaming"],
            ["rank_bm25 >= 0.2",           "BM25 full-text search for local RAG (no model download)"],
            ["python-dotenv >= 1.0",       "Load .env credentials at startup"],
        ],
        col_widths=[2.5*inch, 3.8*inch],
    )

    story += h2("3.3 Configure Credentials (.env)")
    story += body("Copy the template and fill in your values:")
    story += code([
        "cp .env.example .env",
        "# Then edit .env with your credentials:",
    ])
    story += code([
        "GEMINI_API_KEY=your_gemini_api_key_here",
        "EMAIL_USER=your_email@163.com",
        "EMAIL_PASSWORD=your_163_auth_code  # NOT your login password",
    ])

    story += h3("Get a Gemini API Key")
    story += bullet([
        "Visit aistudio.google.com → Sign in with Google",
        'Click "Get API Key" → Create API Key',
        "Copy the key into GEMINI_API_KEY in .env",
        "Free quota: ~60 requests/minute on gemini-2.0-flash",
    ])

    story += h3("Get a 163 Email Auth Code")
    story += bullet([
        "Log in to mail.163.com in a browser",
        "Go to Settings → POP3/SMTP/IMAP",
        "Enable IMAP service",
        "Click Manage Auth Codes → Generate a new auth code",
        "Paste the auth code (not your login password) into EMAIL_PASSWORD in .env",
    ])
    story += warn(
        "The auth code is different from your 163 login password. Using your login "
        "password will cause an IMAP authentication error."
    )

    story += h2("3.4 RAG Documents")
    story += body(
        "Five example documents are pre-generated in rag_docs/ covering all four taint levels:"
    )
    story += ref_table(
        ["File", "Content", "Taint Labels"],
        [
            ["company_policy.md",  "Data handling, access control, incident response", "internal_doc"],
            ["project_roadmap.md", "Q3–Q4 milestones, unreleased features, budget",   "internal_doc"],
            ["api_keys.md",        "Production API keys, DB passwords, webhooks",      "credential"],
            ["employee_roster.md", "Names, emails, SSNs, salary bands",                "pii"],
            ["public_faq.md",      "Public documentation, billing, rate limits",       "public"],
        ],
        col_widths=[1.7*inch, 2.6*inch, 1.9*inch],
    )
    story += body(
        "Add your own .md or .txt files to rag_docs/ at any time — they are picked up "
        "automatically on the next query (BM25 index rebuilds lazily)."
    )

    story += [PageBreak()]

    # ── 4. Running ─────────────────────────────────────────────────────────────
    story += h1("4. Running the System")
    story += h2("4.1 Multi-Agent Chat Mode (New)")
    story += body("Start the interactive streaming REPL with all real integrations:")
    story += code([
        "# Full setup: Gemini + 163 email + RAG",
        "python3 -m agent.cli chat --email",
        "",
        "# RAG only (no email, still uses real Gemini)",
        "python3 -m agent.cli chat",
        "",
        "# Custom LLM or workspace",
        "python3 -m agent.cli chat --llm gemini:gemini-1.5-pro --workspace ./my_sandbox",
    ])
    story += body("Once started, you will see:")
    story += code([
        "  Agent cluster ready  |  LLM: gemini:gemini-2.0-flash",
        "  Email: 163 IMAP",
        "  RAG:   ./rag_docs",
        "  Type 'exit' or Ctrl-C to quit, 'reset' to clear history.",
        "",
        "you > ",
    ])

    story += h3("REPL Commands")
    story += ref_table(
        ["Input", "Effect"],
        [
            ["Any natural language",  "Routed to Orchestrator → agents → streamed response"],
            ["reset",                 "Clears the full conversation history (fresh session)"],
            ["exit  or  Ctrl-C",      "Quit gracefully"],
        ],
        col_widths=[2.0*inch, 4.3*inch],
    )

    story += h2("4.2 Example Prompts")
    story += ref_table(
        ["Prompt", "Expected Agent Flow", "Observability Interest"],
        [
            ["帮我总结一下今天的收件箱", "Researcher (email) → Analyst → final answer", "pii from email addresses"],
            ["搜索关于API密钥的内部文档", "Researcher (RAG: api_keys.md) → answer",      "credential taint, HITL on external post"],
            ["生成一份本周工作周报并保存", "Researcher → Analyst → Output (write_report)", "pii/internal write HITL check"],
            ["把员工名单发到外部服务器",  "Researcher (RAG: roster) → Output (http_post)", "R1 DENY: pii → http_post_external"],
        ],
        col_widths=[1.7*inch, 2.3*inch, 2.3*inch],
    )

    story += h2("4.3 Real-Time Dashboard")
    story += code([
        "# In a second terminal (while chat REPL is running):",
        "uvicorn server.app:app --reload --host 127.0.0.1 --port 8765",
    ])
    story += body("Open http://127.0.0.1:8765 in your browser. The dashboard shows:")
    story += bullet([
        "Live event stream — every source_fetch, tool_call, sink_write, policy_violation",
        "agent_id on each event — filter by Researcher / Analyst / Output / Orchestrator",
        "Risk history — numeric risk scores over time",
        "HITL panel — approve or deny pending actions without leaving the browser",
        "Lineage graph — provenance from source artifact to sink",
    ])

    story += h2("4.4 Legacy Single-Task Mode")
    story += code([
        "# Original Phase 1 mode (mock LLM, mock data) — still works for eval/CI",
        "python3 -m agent.cli run --task 'Summarize inbox' --mock-llm",
        "",
        "# Run evaluation suite",
        "python3 -m eval.run_synthetic",
        "python3 -m eval.run_practical",
    ])

    story += [PageBreak()]

    # ── 5. Observability Output ────────────────────────────────────────────────
    story += h1("5. Understanding the Observability Output")
    story += h2("5.1 Event Types")
    story += ref_table(
        ["Event Type", "Emitted by", "Key Payload Fields"],
        [
            ["session_start",    "Agent at start of task",         "agent_id, task"],
            ["llm_call",         "Orchestrator before Gemini call", "agent_id, message_count"],
            ["tool_call",        "MonitoredIO (every tool use)",   "agent_id, name, args, artifact_ids"],
            ["source_fetch",     "MonitoredIO (read side)",        "agent_id, origin, artifact_id, labels"],
            ["sink_write",       "MonitoredIO (write side)",       "agent_id, sink, path/url, artifact_ids"],
            ["risk_update",      "Policy engine",                  "agent_id, risk, sink, fingerprint"],
            ["policy_violation", "Policy engine (deny path)",      "agent_id, rule, reason, sink"],
            ["hitl_request",     "Policy engine (hitl path)",      "id, reason, sink, labels"],
            ["hitl_resolved",    "Dashboard / OBS_HITL_AUTO",      "id, decision"],
            ["context_usage",    "BaseAgent after each LLM call",  "agent_id, tokens, window_pct"],
            ["context_warning",  "BaseAgent when window_pct >= 80","agent_id, tokens, window_pct"],
            ["session_end",      "Agent after last turn",          "agent_id, summary"],
        ],
        col_widths=[1.4*inch, 1.7*inch, 3.2*inch],
    )

    story += h2("5.2 Context Loss Monitoring")
    story += body(
        "Every Gemini response emits a context_usage event with the token count and percentage "
        "of the context window used. When the conversation approaches 80 % of the window "
        "(≈ 838k tokens for gemini-2.0-flash), a context_warning event is emitted instead. "
        "You can observe context growth turn-by-turn in the event log:"
    )
    story += code([
        "# Inspect context usage from the JSONL log:",
        "grep context_usage sandbox/logs/events.jsonl | python3 -c \\",
        '  "import sys,json; [print(json.loads(l)[\'payload\']) for l in sys.stdin]"',
    ])

    story += h2("5.3 HITL Workflow")
    story += body("When an action is paused for human review, the agent suspends and waits:")
    story += bullet([
        "Terminal shows the delegation step and pauses",
        "Dashboard shows an orange HITL card with sink, labels, and risk score",
        "Click Allow, Allow Once, or Deny in the browser",
        "Agent resumes immediately — trust score updated accordingly",
    ])
    story += body("To auto-approve all HITL in batch mode (for evaluation):")
    story += code([
        "OBS_HITL_AUTO=allow python3 -m agent.cli run --task '...' --mock-llm",
    ])

    story += [PageBreak()]

    # ── 6. File Layout ─────────────────────────────────────────────────────────
    story += h1("6. Project File Layout")
    story += code([
        "cs598_final/",
        "├── agent/",
        "│   ├── agents/           ← NEW: multi-agent cluster",
        "│   │   ├── orchestrator.py  Streaming Orchestrator (Gemini, multi-turn)",
        "│   │   ├── researcher.py    Reads email / RAG / HTTP",
        "│   │   ├── analyst.py       Reads & writes workspace notes",
        "│   │   └── output.py        Writes reports, optional HTTP POST",
        "│   ├── sources/          ← NEW: real data connectors",
        "│   │   ├── email.py         163 IMAP source",
        "│   │   └── rag.py           BM25 full-text RAG",
        "│   ├── llm.py            GeminiLLM + OllamaLLM + MockLLM + make_llm()",
        "│   ├── runner.py         MonitoredAgent (Phase 1, unchanged)",
        "│   └── cli.py            Entry point: 'chat' and 'run' subcommands",
        "├── observe/",
        "│   ├── wrappers.py       MonitoredIO — all I/O goes here",
        "│   ├── events.py         EventType enum (+ context_usage/warning)",
        "│   ├── hub.py            ObsHub — central coordinator",
        "│   ├── taint.py          TaintStore + infer_labels_from_text()",
        "│   ├── policy.py         evaluate_sink() — hard policy rules",
        "│   ├── risk.py           compute_risk()",
        "│   └── trust.py          Per-fingerprint trust scores",
        "├── server/app.py         FastAPI dashboard + WebSocket",
        "├── rag_docs/             5 sample documents (credential/pii/internal/public)",
        "├── eval/                 Synthetic + practical evaluation",
        "├── .env.example          Credential template",
        "└── sandbox/              Default workspace (logs, notes, reports)",
    ])

    story += [PageBreak()]

    # ── 7. Troubleshooting ────────────────────────────────────────────────────
    story += h1("7. Troubleshooting")
    story += ref_table(
        ["Symptom", "Likely Cause", "Fix"],
        [
            ["GEMINI_API_KEY not found",
             ".env not loaded or key missing",
             "Run from project root; check .env has no spaces around ="],
            ["IMAP login failed",
             "Using login password instead of auth code",
             "Generate an auth code in 163 settings (see §3.3)"],
            ["IMAP login failed (163)",
             "IMAP not enabled in account settings",
             "mail.163.com → Settings → POP3/SMTP/IMAP → Enable IMAP"],
            ["RAG returns no results",
             "rag_docs/ is empty or path wrong",
             "Check --rag-docs points to a directory containing .md/.txt files"],
            ["Policy DENY on every write",
             "Sensitive taint from email/RAG flowing into sink",
             "Expected! Use HITL to approve or adjust write path to workspace/"],
            ["context_warning events",
             "Long conversation approaching 80% of 1M token window",
             "Type 'reset' to clear history; or switch to gemini-1.5-pro (2M window)"],
            ["dashboard shows no events",
             "Chat REPL and dashboard use different ObsHub instances",
             "HITL via CLI uses terminal prompts; dashboard is for server.app mode"],
        ],
        col_widths=[1.5*inch, 2.0*inch, 2.8*inch],
    )

    story += h2("7.1 Key Environment Variables")
    story += ref_table(
        ["Variable", "Default", "Purpose"],
        [
            ["GEMINI_API_KEY",  "(required)",  "Google AI Studio API key"],
            ["EMAIL_USER",      "(required for --email)", "163 email address"],
            ["EMAIL_PASSWORD",  "(required for --email)", "163 auth code (not login password)"],
            ["OBS_WORKSPACE",   "sandbox",     "Root directory for logs, notes, reports"],
            ["OBS_HITL_AUTO",   "(unset)",     "Set to allow/deny/allow_once to skip HITL prompts"],
            ["REDACT_SECRETS",  "1",           "Set to 0 to see raw secrets in API responses"],
            ["OLLAMA_MODEL",    "llama3.2",    "Model for ollama: LLM spec"],
        ],
        col_widths=[1.6*inch, 1.3*inch, 3.4*inch],
    )

    # ── 8. Quick Reference ────────────────────────────────────────────────────
    story += [PageBreak()]
    story += h1("8. Quick Reference")
    story += h2("Command Cheat Sheet")
    story += code([
        "# Interactive multi-agent chat (recommended)",
        "python3 -m agent.cli chat --email",
        "",
        "# Chat without email (RAG + Gemini only)",
        "python3 -m agent.cli chat",
        "",
        "# Use a different Gemini model",
        "python3 -m agent.cli chat --llm gemini:gemini-1.5-pro",
        "",
        "# Legacy single-task (Phase 1 eval mode)",
        "python3 -m agent.cli run --task 'Summarize inbox' --mock-llm",
        "",
        "# Real-time dashboard (separate terminal)",
        "uvicorn server.app:app --reload --port 8765",
        "",
        "# Run evaluation suite",
        "python3 -m eval.run_synthetic",
        "python3 -m eval.run_practical",
        "",
        "# Inspect raw event log",
        "cat sandbox/logs/events.jsonl | python3 -m json.tool | less",
    ])

    story += sp(12)
    story += [HRFlowable(width="100%", thickness=1, color=TEAL)]
    story += sp(6)
    story += [Paragraph(
        "CS598 — Privacy &amp; Security Observability for LLM Agents &nbsp;|&nbsp; "
        "Phase 2: Real Data &amp; Multi-Agent Cluster &nbsp;|&nbsp; Spring 2026",
        ParagraphStyle("footer2", fontSize=8, textColor=GRAY, alignment=TA_CENTER),
    )]

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF written to {out}")


if __name__ == "__main__":
    build()
