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

  const svgEl = el("lineage-svg");
  const W = svgEl.clientWidth || 480;
  const H = 280;
  svgEl.setAttribute("height", H);

  const violatedSinks = new Set(
    events
      .filter((e) => e.event_type === "policy_violation")
      .map((e) => `sink:${e.step_id}:${e.payload?.sink}`)
  );

  // Convert nodes dict → array, edges list → links with index references
  const nodesMap = r.nodes || {};
  const rawEdges = r.edges || [];
  const nodes = Object.values(nodesMap).map((n) => ({ ...n }));
  const idToIndex = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  const links = rawEdges
    .filter((e) => idToIndex[e.from] !== undefined && idToIndex[e.to] !== undefined)
    .map((e) => ({ source: idToIndex[e.from], target: idToIndex[e.to], rel: e.rel }));

  // Color helpers
  const kindColor = { source: "#3d8bfd", tool: "#d4a017", sink: "#3fb950" };
  const labelBorder = { credential: "#f85149", pii: "#f0883e", internal_doc: "#e3b341", public: "none" };

  function nodeColor(n) {
    if (n.kind === "sink" && violatedSinks.has(n.id)) return "#f85149";
    return kindColor[n.kind] || "#8b9cb3";
  }

  function nodeBorder(n) {
    const labels = n.labels || [];
    for (const l of ["credential", "pii", "internal_doc"]) {
      if (labels.includes(l)) return labelBorder[l];
    }
    return "#4a5568";
  }

  // Clear and rebuild SVG
  const svg = d3.select(svgEl);
  svg.selectAll("*").remove();

  if (nodes.length === 0) {
    svg.append("text")
      .attr("x", W / 2).attr("y", H / 2)
      .attr("text-anchor", "middle")
      .attr("fill", "#8b9cb3")
      .attr("font-size", "0.85rem")
      .text("No lineage data yet");
    return;
  }

  // Arrowhead marker
  svg.append("defs").append("marker")
    .attr("id", "arrow")
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 22).attr("refY", 0)
    .attr("markerWidth", 6).attr("markerHeight", 6)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M0,-5L10,0L0,5")
    .attr("fill", "#8b9cb3");

  const g = svg.append("g");

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).distance(90).strength(0.8))
    .force("charge", d3.forceManyBody().strength(-220))
    .force("center", d3.forceCenter(W / 2, H / 2))
    .force("collision", d3.forceCollide(32));

  const link = g.append("g").selectAll("line")
    .data(links).join("line")
    .attr("stroke", "#8b9cb3")
    .attr("stroke-width", 1.5)
    .attr("marker-end", "url(#arrow)");

  const linkLabel = g.append("g").selectAll("text")
    .data(links).join("text")
    .attr("fill", "#8b9cb3")
    .attr("font-size", "0.65rem")
    .attr("text-anchor", "middle")
    .text((d) => d.rel);

  const node = g.append("g").selectAll("circle")
    .data(nodes).join("circle")
    .attr("r", 14)
    .attr("fill", nodeColor)
    .attr("stroke", nodeBorder)
    .attr("stroke-width", 2.5)
    .call(
      d3.drag()
        .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  const label = g.append("g").selectAll("text")
    .data(nodes).join("text")
    .attr("text-anchor", "middle")
    .attr("dy", "2.2em")
    .attr("fill", "#e7ecf3")
    .attr("font-size", "0.7rem")
    .text((d) => d.name || d.origin || d.sink || d.id.split(":").pop());

  node.append("title").text((d) => `${d.kind}: ${d.id}\nlabels: ${(d.labels || []).join(", ") || "—"}`);

  sim.on("tick", () => {
    link
      .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
    linkLabel
      .attr("x", (d) => (d.source.x + d.target.x) / 2)
      .attr("y", (d) => (d.source.y + d.target.y) / 2);
    node.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
    label.attr("x", (d) => d.x).attr("y", (d) => d.y);
  });
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
