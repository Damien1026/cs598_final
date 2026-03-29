const API = "";

let ws;
const events = [];
let reveal = false;

function el(id) {
  return document.getElementById(id);
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "event") {
      events.push(msg.data);
      renderAll();
      maybeHitl(msg.data);
    }
  };
  ws.onclose = () => setTimeout(connectWs, 2000);
}

function maybeHitl(data) {
  if (data.event_type !== "hitl_request") return;
  const p = data.payload || {};
  el("hitl-panel").classList.remove("hidden");
  el("hitl-reason").textContent = p.reason || "Review required";
  el("hitl-detail").textContent = JSON.stringify(p, null, 2);
  el("hitl-panel").dataset.hid = p.id;
}

async function postHitl(decision) {
  const hid = el("hitl-panel").dataset.hid;
  if (!hid) return;
  await fetch(`${API}/api/hitl/${hid}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  el("hitl-panel").classList.add("hidden");
}

function renderTimeline() {
  const typeF = el("filter-type").value;
  const q = (el("filter-q").value || "").toLowerCase();
  const box = el("timeline");
  box.innerHTML = "";
  for (const e of events) {
    if (typeF && e.event_type !== typeF) continue;
    const blob = JSON.stringify(e.payload || {}).toLowerCase();
    if (q && !blob.includes(q)) continue;
    const div = document.createElement("div");
    div.className = "ev " + e.event_type;
    div.innerHTML = `<div class="ev-type">${e.event_type} · step ${e.step_id}</div><pre>${escapeHtml(
      JSON.stringify(e.payload, null, 2)
    )}</pre>`;
    box.appendChild(div);
  }
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderRisk() {
  const hist = events.filter((e) => e.event_type === "risk_update");
  const last = hist.length ? hist[hist.length - 1].payload : null;
  const r = last ? last.risk : 0;
  el("risk-bar").style.width = `${Math.min(100, r * 100)}%`;
  el("risk-text").textContent = last
    ? `Last: ${r.toFixed(2)} (sink ${last.sink || "—"})`
    : "No risk updates yet";

  const ul = el("risk-list");
  ul.innerHTML = "";
  hist.slice(-8).forEach((e) => {
    const li = document.createElement("li");
    li.textContent = `${e.payload.risk?.toFixed(2)} · ${e.payload.sink}`;
    ul.appendChild(li);
  });
}

async function renderLineage() {
  const r = await fetch(`${API}/api/lineage`).then((x) => x.json());
  el("lineage").textContent = JSON.stringify(r, null, 2);
}

function renderFilters() {
  const sel = el("filter-type");
  const types = [...new Set(events.map((e) => e.event_type))].sort();
  const cur = sel.value;
  sel.innerHTML = '<option value="">all</option>';
  types.forEach((t) => {
    const o = document.createElement("option");
    o.value = t;
    o.textContent = t;
    sel.appendChild(o);
  });
  sel.value = types.includes(cur) ? cur : "";
}

function renderAll() {
  renderFilters();
  renderTimeline();
  renderRisk();
  renderLineage();
}

el("start").onclick = async () => {
  events.length = 0;
  reveal = el("reveal").checked;
  const task = el("task").value;
  const mock = el("mock").checked;
  await fetch(`${API}/api/agent/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, mock_llm: mock }),
  });
};

el("reveal").onchange = () => {
  reveal = el("reveal").checked;
  refreshFromApi();
};

async function refreshFromApi() {
  const r = await fetch(`${API}/api/events?reveal=${reveal}`).then((x) => x.json());
  el("session").textContent = `trace: ${r.trace_id?.slice(0, 8)}…`;
  events.length = 0;
  events.push(...(r.events || []));
  renderAll();
}

document.querySelectorAll(".hitl-actions button").forEach((b) => {
  b.onclick = () => postHitl(b.dataset.decision);
});

el("filter-type").onchange = renderTimeline;
el("filter-q").oninput = renderTimeline;

connectWs();
refreshFromApi();
setInterval(refreshFromApi, 4000);
