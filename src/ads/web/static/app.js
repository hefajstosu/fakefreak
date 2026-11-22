// Web panel. Every value from the server goes into the DOM as text (never innerHTML): it comes from scam pages.
"use strict";

const SCAM = {
  fake_investment: "fałszywa inwestycja", fake_online_casino: "fałszywe kasyno", miracle_cure: "cudowny lek",
  banking_phishing: "phishing bankowy", fake_giveaway: "fałszywe rozdanie", fake_subsidy_or_payout: "fałszywa dopłata / wypłata",
  fake_online_shop: "fałszywy sklep", political_disinformation: "dezinformacja polityczna",
  impersonation_other: "podszywanie się (inne)", not_suspicious: "niepodejrzane", other: "inne",
};
const STATUS = {  // decision status -> [css class, heading]
  duplicate: ["ok", "Duplikat sprawy, która już jest w bazie"],
  same_content: ["ok", "Ta sama treść co znana kampania, inny host"],
  confirmed: ["ok", "Pasuje do znanej kampanii (potwierdzone twardym dowodem)"],
  likely: ["info", "Prawdopodobnie znana kampania"],
  suggested_family: ["warn", "Przypomina znaną rodzinę oszustw, za słabo na kampanię"],
  new_unconfirmed: ["warn", "Nowa kampania (do potwierdzenia przez analityka)"],
};

const $ = (id) => document.getElementById(id);
let analysisId = null;
let joined = [];

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c != null) node.append(c);
  return node;
}

function casesPl(n) {
  if (n === 1) return "1 sprawa";
  return [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? `${n} sprawy` : `${n} spraw`;
}

async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ error: `Błąd serwera (${res.status})` }));
  if (!res.ok) throw new Error(data.error || `Błąd serwera (${res.status})`);
  return data;
}

const tau = () => Number($("tau").value);

// ---------------------------------------------------------------- one case card (database case or the new article)
function caseCard(s, title) {
  const rows = [
    ["Typ", `${SCAM[s.scam_type] || s.scam_type} · ${s.topic}`],
    ["Produkt", s.product || "–"],
    ["Osoby", s.people.join(", ") || "–"],
    ["Podszywa się", s.media.join(", ") || "–"],
    ["Szablon", s.templates],
    ["Domeny", s.domains.join(", ") || "–"],
    ["Trackery", String(s.trackers.length)],
  ];
  const dl = el("dl", {}, rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })]));
  const chips = el("div", { class: "chips" }, s.persuasion.map((p) => el("span", { class: "chip", text: p.replaceAll("_", " ") })));
  const body = el("div", {}, [
    el("h4", { text: title + (s.unconfirmed ? " · niepotwierdzona" : "") }), dl,
    s.persuasion.length ? el("div", { class: "summary" }, chips) : null,
    el("p", { class: "summary", text: s.summary, title: s.summary }),
  ]);
  const img = s.image_url ? el("img", { src: s.image_url, alt: `Zrzut reklamy, sprawa ${s.case}`, loading: "lazy", width: "96", height: "128" }) : null;
  return el("article", { class: "case" + (img ? "" : " noimg"), id: s.case === "new" ? null : `case-${s.case}` }, [img, body]);
}

// ---------------------------------------------------------------- groups
async function loadGroups() {
  const box = $("groups");
  try {
    const data = await api(`/api/groups?tau=${tau()}`);
    $("groups-hint").textContent = `Kampania = sprawy połączone twardym dowodem albo średnim podobieństwem ≥ τ = ${data.tau.toFixed(2)}. ` +
      "Rodzina = kampanie z tym samym typem oszustwa.";
    box.replaceChildren(...data.groups.map(groupCard));
  } catch (e) {
    box.replaceChildren(el("p", { class: "message error", text: `Nie udało się wczytać grup: ${e.message}` }));
  }
}

function groupCard(g) {
  const ids = g.members.map((m) => m.case);
  const hit = joined.some((j) => j.length === ids.length && j.every((c) => ids.includes(c)));
  const summary = el("summary", {}, [
    el("span", { class: "group-title", text: `Kampania ${g.no}` }),
    el("span", { class: "badge", text: `rodzina ${g.family}` }),
    el("span", { class: "badge", text: SCAM[g.scam_type] || g.scam_type }),
    el("span", { class: "badge", text: casesPl(ids.length) }),
    el("span", { class: "group-ids", text: ids.join(", ") }),
    hit ? el("span", { class: "badge hit", text: "pasuje nowy artykuł" }) : null,
  ]);
  const links = g.links.slice(0, 8).map((l) => el("li", {}, [
    `${l.a} ↔ ${l.b}: podobieństwo ${l.score.toFixed(2)}`,
    l.evidence.length ? el("span", { class: "ev", text: ` · ${l.evidence.join("; ")}` }) : " · brak twardych dowodów",
  ]));
  const body = el("div", { class: "group-body" }, [
    links.length ? el("ul", { class: "links" }, links) : null,
    el("div", { class: "cases" }, g.members.map((m) => caseCard(m, `Sprawa ${m.case}`))),
  ]);
  const card = el("details", { class: "group" + (hit ? " hit" : "") }, [summary, body]);
  card.open = hit;
  return card;
}

// ---------------------------------------------------------------- analysis
function showResult(r) {
  const [cls, heading] = STATUS[r.decision.status] || ["info", r.decision.status];
  $("decision").className = `decision ${cls}`;
  $("decision").replaceChildren(el("strong", { text: heading }), `${r.decision.title}. ${r.decision.explanation}`);
  const notes = [...r.notes];
  if (!r.llm_used) notes.push("duplikat rozpoznany bez wywołania LLM (użyto profilu z bazy)");
  $("notes").textContent = notes.length ? `Skan strony: ${notes.join("; ")}` : "";
  $("profile").replaceChildren(el("div", { class: "cases" }, caseCard(r.profile, "Analizowany artykuł")));
  $("neighbours").tBodies[0].replaceChildren(...r.neighbours.map((n) => el("tr", {}, [
    el("td", {}, el("a", { href: `#case-${n.case}`, text: n.case })),
    el("td", { class: "num" }, [el("span", { class: "bar", style: `width:${Math.round(n.score * 80)}px` }), n.score.toFixed(2)]),
    el("td", { text: n.product || "–" }),
    el("td", { text: n.evidence.join("; ") || "–" }),
  ])));
  $("save-btn").disabled = false;
  $("save-msg").textContent = "Kolejne artykuły będą porównywane także z tym.";
  $("result").hidden = false;
}

$("analyse-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = $("url").value.trim();
  const text = $("text").value.trim();
  const msg = $("form-msg");
  msg.className = "message";
  if (!url && !text) {
    msg.className = "message error";
    msg.textContent = "Podaj adres URL albo wklej tekst artykułu.";
    return;
  }
  $("analyse-btn").disabled = true;
  msg.textContent = "Pobieram stronę i porównuję z bazą… (zwykle 5–15 s)";
  try {
    const r = await api("/api/analyze", { url, text, tau: tau() });
    analysisId = r.id;
    joined = r.joins;
    showResult(r);
    msg.textContent = "";
    await loadGroups();
    $("result").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  } catch (e) {
    msg.className = "message error";
    msg.textContent = e.message;
  } finally {
    $("analyse-btn").disabled = false;
  }
});

$("save-btn").addEventListener("click", async () => {
  $("save-btn").disabled = true;
  try {
    const r = await api("/api/save", { id: analysisId });
    $("save-msg").textContent = `Zapisano jako ${r.case_id} (lokalnie, data/cases; poza gitem).`;
    joined = [];
    await Promise.all([loadStatus(), loadGroups()]);
  } catch (e) {
    $("save-msg").textContent = e.message;
    $("save-btn").disabled = false;
  }
});

$("tau").addEventListener("input", () => { $("tau-out").textContent = tau().toFixed(2); });
$("tau").addEventListener("change", () => { joined = []; loadGroups(); });

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const parts = [el("b", { text: casesPl(s.cases) }), " w bazie · "];
    parts.push(s.llm ? "LLM: gotowy" : el("span", { class: "warn", text: "brak klucza LLM: analiza nowych artykułów wyłączona" }));
    $("status").replaceChildren(...parts);
    $("analyse-btn").disabled = !s.llm;
  } catch (e) {
    $("status").textContent = "Serwer nie odpowiada.";
  }
}

loadStatus();
loadGroups();
