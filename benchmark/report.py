"""Generate a standalone HTML comparison report with Chart.js charts."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmark.run_comparison import BenchmarkRun, TaskResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group(results: list["TaskResult"]) -> dict[str, dict[str, "TaskResult"]]:
    """Returns {task_id: {model: result}}"""
    groups: dict[str, dict[str, "TaskResult"]] = {}
    for r in results:
        groups.setdefault(r.task_id, {})[r.model] = r
    return groups


TASK_ORDER = ["summarize", "extract", "prioritize"]
TASK_LABELS = {
    "summarize": "Inbox Summary",
    "extract": "Structured Extraction",
    "prioritize": "Priority & Action",
}

MODEL_COLORS = [
    ("rgba(66, 133, 244, 0.85)", "rgba(66, 133, 244, 1)"),    # Google Blue
    ("rgba(0, 191, 165, 0.85)", "rgba(0, 191, 165, 1)"),       # DeepSeek Teal
    ("rgba(255, 160, 0, 0.85)", "rgba(255, 160, 0, 1)"),        # Amber
    ("rgba(234, 67, 53, 0.85)", "rgba(234, 67, 53, 1)"),        # Red
]

# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_report(run: "BenchmarkRun", out_path: Path) -> None:
    groups = _group(run.results)
    task_ids = [t for t in TASK_ORDER if t in groups]
    task_labels = [TASK_LABELS.get(t, t) for t in task_ids]
    models = run.models

    # Build chart datasets
    latency_datasets = []
    token_datasets = []
    for i, model in enumerate(models):
        color_fill, color_border = MODEL_COLORS[i % len(MODEL_COLORS)]
        latencies = [groups.get(tid, {}).get(model, None) for tid in task_ids]
        tokens = [groups.get(tid, {}).get(model, None) for tid in task_ids]
        latency_datasets.append({
            "label": model,
            "data": [r.latency_s if r and not r.error else None for r in latencies],
            "backgroundColor": color_fill,
            "borderColor": color_border,
            "borderWidth": 2,
            "borderRadius": 6,
        })
        token_datasets.append({
            "label": model,
            "data": [r.tokens if r and not r.error else None for r in tokens],
            "backgroundColor": color_fill,
            "borderColor": color_border,
            "borderWidth": 2,
            "borderRadius": 6,
        })

    # Summary stats cards
    summary_cards_html = ""
    for model in models:
        model_results = [r for r in run.results if r.model == model and not r.error]
        if model_results:
            avg_lat = round(sum(r.latency_s for r in model_results) / len(model_results), 2)
            total_tok = sum(r.tokens for r in model_results)
            success = len(model_results)
        else:
            avg_lat, total_tok, success = 0, 0, 0
        short = model.split(":")[-1] if ":" in model else model
        summary_cards_html += f"""
        <div class="stat-card">
            <div class="stat-model">{html.escape(short)}</div>
            <div class="stat-row"><span class="stat-label">Avg Latency</span><span class="stat-value">{avg_lat}s</span></div>
            <div class="stat-row"><span class="stat-label">Total Tokens</span><span class="stat-value">{total_tok:,}</span></div>
            <div class="stat-row"><span class="stat-label">Tasks OK</span><span class="stat-value">{success}/{len(TASK_ORDER)}</span></div>
        </div>"""

    # Per-task output comparison tables
    task_sections_html = ""
    for tid in task_ids:
        task_results = groups.get(tid, {})
        task_name = TASK_LABELS.get(tid, tid)
        cols_html = ""
        for model in models:
            r = task_results.get(model)
            if r and not r.error:
                output_text = html.escape(r.output)
                meta = f"{r.latency_s}s · {r.tokens} tokens"
                cols_html += f"""
                <div class="output-col">
                    <div class="output-model">{html.escape(model)}</div>
                    <div class="output-meta">{meta}</div>
                    <pre class="output-text">{output_text}</pre>
                </div>"""
            elif r and r.error:
                cols_html += f"""
                <div class="output-col output-error">
                    <div class="output-model">{html.escape(model)}</div>
                    <div class="output-meta error-label">Error</div>
                    <pre class="output-text">{html.escape(r.error)}</pre>
                </div>"""
            else:
                cols_html += f"""
                <div class="output-col output-empty">
                    <div class="output-model">{html.escape(model)}</div>
                    <div class="output-meta">—</div>
                </div>"""
        task_sections_html += f"""
        <div class="task-section">
            <h3 class="task-title">{html.escape(task_name)}</h3>
            <div class="output-grid" style="--cols: {len(models)}">
                {cols_html}
            </div>
        </div>"""

    chart_data_json = json.dumps({
        "labels": task_labels,
        "latency": latency_datasets,
        "tokens": token_datasets,
    })

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM Comparison — CS598</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f8f9fa; color: #212529; line-height: 1.5; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}

  /* Header */
  .report-header {{ margin-bottom: 32px; border-bottom: 2px solid #dee2e6; padding-bottom: 16px; }}
  .report-header h1 {{ font-size: 1.75rem; font-weight: 700; color: #1a1a2e; }}
  .report-meta {{ color: #6c757d; font-size: 0.875rem; margin-top: 6px; }}

  /* Summary cards */
  .summary-row {{ display: flex; gap: 16px; margin-bottom: 40px; flex-wrap: wrap; }}
  .stat-card {{ background: #fff; border: 1px solid #dee2e6; border-radius: 12px;
               padding: 20px 24px; flex: 1; min-width: 180px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .stat-model {{ font-size: 0.8rem; font-weight: 600; color: #6c757d; text-transform: uppercase;
                letter-spacing: .04em; margin-bottom: 12px; }}
  .stat-row {{ display: flex; justify-content: space-between; align-items: center;
              padding: 4px 0; border-bottom: 1px solid #f1f3f5; }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-label {{ color: #495057; font-size: 0.875rem; }}
  .stat-value {{ font-weight: 600; font-size: 0.95rem; color: #1a1a2e; }}

  /* Charts */
  .charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 48px; }}
  @media (max-width: 700px) {{ .charts-grid {{ grid-template-columns: 1fr; }} }}
  .chart-card {{ background: #fff; border: 1px solid #dee2e6; border-radius: 12px;
                padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .chart-card h2 {{ font-size: 1rem; font-weight: 600; color: #343a40; margin-bottom: 16px; }}
  canvas {{ max-height: 280px; }}

  /* Task outputs */
  h2.section-title {{ font-size: 1.2rem; font-weight: 700; color: #1a1a2e; margin-bottom: 20px; }}
  .task-section {{ margin-bottom: 36px; }}
  .task-title {{ font-size: 1rem; font-weight: 600; color: #495057; margin-bottom: 12px;
                padding-left: 10px; border-left: 3px solid #4285f4; }}
  .output-grid {{ display: grid; grid-template-columns: repeat(var(--cols, 2), 1fr); gap: 16px; }}
  @media (max-width: 700px) {{ .output-grid {{ grid-template-columns: 1fr; }} }}
  .output-col {{ background: #fff; border: 1px solid #dee2e6; border-radius: 10px;
                overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.05); }}
  .output-model {{ background: #f1f3f5; padding: 8px 14px; font-size: 0.78rem;
                  font-weight: 600; color: #495057; text-transform: uppercase; letter-spacing: .04em; }}
  .output-meta {{ padding: 4px 14px; font-size: 0.8rem; color: #868e96; background: #f8f9fa;
                 border-bottom: 1px solid #e9ecef; }}
  .output-text {{ padding: 14px; font-size: 0.82rem; white-space: pre-wrap; word-break: break-word;
                 max-height: 360px; overflow-y: auto; color: #212529; font-family: "SF Mono", "Fira Mono", monospace; }}
  .output-error .output-model {{ background: #fff5f5; color: #c0392b; }}
  .error-label {{ color: #c0392b !important; }}
  .output-empty {{ opacity: .5; }}
</style>
</head>
<body>
<div class="container">

  <div class="report-header">
    <h1>LLM Comparison Report</h1>
    <div class="report-meta">
      CS598 · Generated {html.escape(run.timestamp)} · Email source: {html.escape(run.email_source)} · Models: {html.escape(', '.join(run.models))}
    </div>
  </div>

  <div class="summary-row">
    {summary_cards_html}
  </div>

  <div class="charts-grid">
    <div class="chart-card">
      <h2>Response Latency (seconds)</h2>
      <canvas id="chartLatency"></canvas>
    </div>
    <div class="chart-card">
      <h2>Token Usage</h2>
      <canvas id="chartTokens"></canvas>
    </div>
  </div>

  <h2 class="section-title">Task Outputs</h2>
  {task_sections_html}

</div>

<script>
const DATA = {chart_data_json};
const chartOpts = (title) => ({{
  responsive: true,
  plugins: {{
    legend: {{ position: "top", labels: {{ font: {{ size: 12 }} }} }},
    tooltip: {{ mode: "index", intersect: false }},
  }},
  scales: {{
    x: {{ grid: {{ display: false }} }},
    y: {{ beginAtZero: true, grid: {{ color: "rgba(0,0,0,.06)" }} }},
  }},
}});

new Chart(document.getElementById("chartLatency"), {{
  type: "bar",
  data: {{ labels: DATA.labels, datasets: DATA.latency }},
  options: chartOpts("Latency (s)"),
}});

new Chart(document.getElementById("chartTokens"), {{
  type: "bar",
  data: {{ labels: DATA.labels, datasets: DATA.tokens }},
  options: chartOpts("Tokens"),
}});
</script>
</body>
</html>"""

    out_path.write_text(html_content, encoding="utf-8")
