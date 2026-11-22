// The graph tab: cases coloured by campaign, families framed, links by kind of evidence (width = score).
import { $, api, el, f2, note, svg, tau } from "./dom.js";
import { evRaw, pretty } from "./labels.js";
import { state } from "./state.js";
import { showPair } from "./explain.js";
import { openCase } from "./tabs.js";

const PALETTE = ["#1c4f8a", "#17643a", "#9a5b00", "#6b4fa0", "#2f7f95", "#8a3b12", "#4d5a1e", "#7a2e5c"];
const KIND = { hard: "twardy dowód", same: "ta sama kampania", famev: "dowód rodziny", fam: "różne kampanie" };
const W = 960, GAP = 34, NODE = 17;

function layout(nodes) {
  // campaigns of one family side by side; members on a circle around the campaign centre; rows wrap at W
  const camps = new Map();
  for (const n of nodes) {
    if (!camps.has(n.campaign)) camps.set(n.campaign, { no: n.campaign, family: n.family, members: [] });
    camps.get(n.campaign).members.push(n);
  }
  const list = [...camps.values()].sort((a, b) => a.family - b.family || b.members.length - a.members.length || a.no - b.no);
  const pos = new Map(), boxes = [], famBox = new Map();
  let x = GAP, y = GAP + 12, rowH = 0, used = 0;
  for (const c of list) {
    const k = c.members.length;
    const r = k === 1 ? 0 : Math.max(38, (k * (NODE * 2 + 14)) / (2 * Math.PI));
    const size = 2 * (r + NODE) + 10;
    if (x + size > W - GAP && x > GAP) { x = GAP; y += rowH + GAP; rowH = 0; }
    c.members.forEach((m, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / k;
      pos.set(m.case, [x + size / 2 + r * Math.cos(a), y + size / 2 + r * Math.sin(a)]);
    });
    boxes.push({ c, x, y });
    const f = famBox.get(c.family) || { x0: x, y0: y, x1: x + size, y1: y + size, n: 0 };
    famBox.set(c.family, { x0: Math.min(f.x0, x), y0: Math.min(f.y0, y), x1: Math.max(f.x1, x + size), y1: Math.max(f.y1, y + size), n: f.n + 1 });
    x += size + GAP;
    used = Math.max(used, x);
    rowH = Math.max(rowH, size);
  }
  return { pos, boxes, famBox, width: Math.max(used, W / 2.2), height: y + rowH + GAP };  // small graphs drawn larger
}

const edgeClass = (e) => (e.must_link ? "hard" : e.same_campaign ? "same" : e.family_link ? "famev" : "fam");
const evidenceText = (e) => (e.evidence.length ? e.evidence.map(evRaw).join("; ") : "");
const openEdge = (e) => showPair("graph-pair", e.a, e.b);

function drawGraph(g) {
  $("graph-hint").textContent = `τ = ${f2(g.tau)}. Krawędzie: każda para z dowodem oraz do 4 najsilniejszych powiązań każdej sprawy z wynikiem ≥ ${f2(g.family_score)} (próg rodziny).`;
  if (!g.nodes.length) {
    $("graph").replaceChildren(note("Baza jest pusta."));
    return;
  }
  const L = layout(g.nodes);
  const size = new Map();
  for (const n of g.nodes) size.set(n.campaign, (size.get(n.campaign) || 0) + 1);
  const root = svg("svg", { viewBox: `0 0 ${L.width} ${L.height}`, class: "graph-svg", role: "group", "aria-label": "Graf powiązań między sprawami" });
  for (const [fam, f] of L.famBox) {
    if (f.n > 1) {
      root.append(svg("rect", { x: f.x0 - 10, y: f.y0 - 10, width: f.x1 - f.x0 + 20, height: f.y1 - f.y0 + 20, class: "fam-box" }),
        svg("text", { x: f.x0 - 4, y: f.y0 - 14, class: "fam-label" }, `rodzina ${fam}`));
    }
  }
  for (const b of L.boxes.filter((x) => x.c.members.length > 1)) root.append(svg("text", { x: b.x + 2, y: b.y + 8, class: "camp-label" }, `K${b.c.no}`));
  for (const e of [...g.edges].sort((p, q) => p.score - q.score)) {
    const [x1, y1] = L.pos.get(e.a), [x2, y2] = L.pos.get(e.b);
    const hit = svg("line", { x1, y1, x2, y2, class: "edge-hit" }, svg("title", {}, `${e.a} ↔ ${e.b}: ${f2(e.score)} ${evidenceText(e)}`));
    hit.addEventListener("click", () => openEdge(e));
    root.append(svg("line", { x1, y1, x2, y2, class: `edge ${edgeClass(e)}`, "stroke-width": (1 + 5 * e.score).toFixed(1) }), hit);
  }
  for (const n of g.nodes) {
    const [x, y] = L.pos.get(n.case);
    const inCampaign = size.get(n.campaign) > 1;
    const node = svg("g", { class: "node", tabindex: "0", role: "button", "aria-label": `Sprawa ${n.case}, kampania K${n.campaign}` }, [
      svg("title", {}, `Sprawa ${n.case} · K${n.campaign} · ${pretty(n.scam_type)}${n.product ? " · " + n.product : ""}`),
      svg("circle", { cx: x, cy: y, r: NODE, fill: inCampaign ? PALETTE[(n.campaign - 1) % PALETTE.length] : "#ffffff", class: inCampaign ? "" : "single" }),
      svg("text", { x, y: y + 4, "text-anchor": "middle", class: inCampaign ? "on-dark" : "" }, n.case),
    ]);
    node.addEventListener("click", () => openCase(n.case));
    node.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openCase(n.case); } });
    root.append(node);
  }
  $("graph").replaceChildren(root);
  $("edge-count").textContent = `[${g.edges.length}]`;
  $("edge-list").replaceChildren(el("ul", { class: "links" }, [...g.edges].sort((p, q) => q.score - p.score).map((e) => {
    const btn = el("button", { type: "button", class: "link-btn why", text: "Dlaczego?" });
    btn.addEventListener("click", () => openEdge(e));
    return el("li", {}, [el("span", { class: "pair", text: `${e.a} ↔ ${e.b}` }), el("span", { class: "sc", text: f2(e.score) }),
      el("span", { class: e.must_link || e.family_link ? "ev" : "none", text: [KIND[edgeClass(e)], evidenceText(e)].filter(Boolean).join(": ") }), btn]);
  })));
}

export async function loadGraph() {
  if (state.graphTau === tau()) return;
  $("graph").replaceChildren(note("Rysuję graf…"));
  try {
    const g = await api(`/api/graph?tau=${tau()}`);
    state.graphTau = g.tau;
    drawGraph(g);
  } catch (e) {
    $("graph").replaceChildren(note(`Nie udało się wczytać grafu: ${e.message}`, "message error"));
  }
}
