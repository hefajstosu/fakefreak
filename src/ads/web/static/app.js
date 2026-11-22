// Web panel. Every value from the server goes into the DOM as text (never innerHTML): it comes from scam pages.
"use strict";

const SCAM = {
  fake_investment: "fałszywa inwestycja", fake_online_casino: "fałszywe kasyno", miracle_cure: "cudowny lek",
  banking_phishing: "phishing bankowy", fake_giveaway: "fałszywe rozdanie", fake_subsidy_or_payout: "fałszywa dopłata / wypłata",
  fake_online_shop: "fałszywy sklep", political_disinformation: "dezinformacja polityczna",
  impersonation_other: "podszywanie się (inne)", not_suspicious: "niepodejrzane", other: "inne",
};
const STATUS = {  // decision status -> [css class, stamp, heading]
  duplicate: ["ok", "Duplikat", "Ta sprawa już jest w bazie"],
  same_content: ["ok", "Ta sama treść", "Treść znanej kampanii na innym hoście"],
  confirmed: ["ok", "Potwierdzona", "Pasuje do znanej kampanii (twardy dowód)"],
  likely: ["info", "Prawdopodobna", "Prawdopodobnie znana kampania"],
  suggested_family: ["warn", "Możliwa rodzina", "Przypomina znaną rodzinę oszustw, za słabo na kampanię"],
  new_unconfirmed: ["warn", "Nowa", "Nowa kampania, do potwierdzenia przez analityka"],
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
const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");

// ---------------------------------------------------------------- tabs
const TABS = { analizator: ["tab-analiza", "panel-analiza"], grupy: ["tab-grupy", "panel-grupy"] };

function showTab(name, focus = false) {
  for (const [key, [tabId, panelId]] of Object.entries(TABS)) {
    const on = key === name;
    $(tabId).setAttribute("aria-selected", String(on));
    $(tabId).tabIndex = on ? 0 : -1;
    $(panelId).hidden = !on;
  }
  if (focus) $(TABS[name][0]).focus();
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

for (const [key, [tabId]] of Object.entries(TABS)) {
  $(tabId).addEventListener("click", () => showTab(key));
  $(tabId).addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
      ev.preventDefault();
      showTab(key === "analizator" ? "grupy" : "analizator", true);
    }
  });
}

function openCase(cid) {
  showTab("grupy");
  const card = document.getElementById(`case-${cid}`);
  if (!card) return;
  card.closest("details").open = true;
  card.scrollIntoView({ behavior: smooth(), block: "center" });
  card.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- one case card (database case or the new article)
function caseCard(s, title) {
  const rows = [
    ["Typ", `${SCAM[s.scam_type] || s.scam_type} · ${s.topic}`],
    ["Produkt", s.product || "–"],
    ["Osoby", s.people.join(", ") || "–"],
    ["Podszywa się", s.media.join(", ") || "–"],
    ["Szablon", s.templates.replace(" -> ", " → ")],
    ["Domeny", s.domains.join(", ") || "–"],
    ["Trackery", String(s.trackers.length)],
  ];
  const fields = el("dl", { class: "fields" }, rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })]));
  const head = el("div", { class: "case-title" }, [
    el("h4", { text: title }),
    s.unconfirmed ? el("span", { class: "tag flag", text: "niepotwierdzona" }) : null,
  ]);
  const body = el("div", { class: "case-body" }, [
    head, fields,
    s.persuasion.length ? el("div", { class: "tags" }, s.persuasion.map((p) => el("span", { class: "tag", text: p.replaceAll("_", " ") }))) : null,
    el("p", { class: "summary", text: s.summary, title: s.summary }),
  ]);
  const img = s.image_url
    ? el("figure", {}, el("img", { src: s.image_url, alt: `Zrzut reklamy, sprawa ${s.case}`, loading: "lazy", width: "110", height: "150" }))
    : null;
  const id = s.case === "new" ? null : `case-${s.case}`;
  return el("article", { class: "case" + (img ? "" : " noimg"), id, tabindex: id ? "-1" : null }, [img, body]);
}

// ---------------------------------------------------------------- groups tab
async function loadGroups() {
  const box = $("groups");
  try {
    const data = await api(`/api/groups?tau=${tau()}`);
    $("groups-hint").textContent = `Kampania: sprawy połączone twardym dowodem albo średnim podobieństwem ≥ τ = ${data.tau.toFixed(2)}. ` +
      "Rodzina: kampanie z tym samym typem oszustwa.";
    $("groups-count").textContent = `[${data.groups.length}]`;
    box.replaceChildren(el("div", { class: "groups" }, data.groups.map(groupRow)));
  } catch (e) {
    box.replaceChildren(el("p", { class: "message error", text: `Nie udało się wczytać grup: ${e.message}` }));
  }
}

function groupRow(g) {
  const ids = g.members.map((m) => m.case);
  const hit = joined.some((j) => j.length === ids.length && j.every((c) => ids.includes(c)));
  const summary = el("summary", {}, [
    el("span", { class: "g-no", text: `K${g.no}` }),
    el("span", { class: "g-fam", text: `rodzina ${g.family}` }),
    el("span", { class: "g-main" }, [
      el("span", { class: "g-type", text: SCAM[g.scam_type] || g.scam_type }),
      el("span", { class: "g-ids", text: ids.join(" · ") }),
      hit ? el("span", { class: "tag solid", text: "pasuje nowy artykuł" }) : null,
    ]),
    el("span", { class: "g-count", text: casesPl(ids.length) }),
  ]);
  const links = g.links.slice(0, 8).map((l) => el("li", {}, [
    el("span", { class: "pair", text: `${l.a} ↔ ${l.b}` }),
    el("span", { class: "sc", text: l.score.toFixed(2) }),
    l.evidence.length ? el("span", { class: "ev", text: l.evidence.join("; ") }) : el("span", { class: "none", text: "brak twardych dowodów" }),
  ]));
  const body = el("div", { class: "group-body" }, [
    links.length ? el("ul", { class: "links", "aria-label": "Powiązania między sprawami" }, links) : null,
    el("div", { class: "cases" }, g.members.map((m) => caseCard(m, `Sprawa ${m.case}`))),
  ]);
  const row = el("details", { class: "group" + (hit ? " hit" : "") }, [summary, body]);
  row.open = hit;
  return row;
}

// ---------------------------------------------------------------- analyser tab
function showResult(r) {
  const [cls, stamp, heading] = STATUS[r.decision.status] || ["info", r.decision.status, r.decision.status];
  $("verdict-code").textContent = r.decision.status;
  const notes = [...r.notes];
  if (!r.llm_used) notes.push("duplikat rozpoznany bez wywołania LLM (użyto profilu z bazy)");
  $("decision").replaceChildren(...[
    el("span", { class: `stamp ${cls}`, text: stamp }),
    el("strong", { text: heading }),
    el("p", { text: `${r.decision.title}. ${r.decision.explanation}` }),
    notes.length ? el("p", { class: "notes", text: `Skan strony: ${notes.join("; ")}` }) : null,
  ].filter(Boolean));
  $("profile").replaceChildren(caseCard(r.profile, "Analizowany artykuł"));
  $("neighbours").tBodies[0].replaceChildren(...r.neighbours.map((n) => {
    const link = el("a", { href: "#grupy", text: n.case });
    link.addEventListener("click", (ev) => { ev.preventDefault(); openCase(n.case); });
    const meter = el("span", { class: "meter", "aria-hidden": "true" }, el("i", { style: `width:${Math.round(n.score * 100)}%` }));
    return el("tr", {}, [
      el("td", {}, link),
      el("td", { class: "num" }, [meter, n.score.toFixed(2)]),
      el("td", { text: n.product || "–" }),
      el("td", { class: n.evidence.length ? "ev" : null, text: n.evidence.join("; ") || "–" }),
    ]);
  }));
  $("save-btn").disabled = false;
  $("save-msg").textContent = "";
  $("result").hidden = false;
}

$("analyse-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = $("url").value.trim();
  const text = $("text").value.trim();
  const msg = $("form-msg");
  if (!url && !text) {
    msg.className = "message error";
    msg.textContent = "Podaj adres URL albo wklej tekst artykułu.";
    return;
  }
  $("analyse-btn").disabled = true;
  msg.className = "message busy";
  msg.textContent = "Pobieram stronę i porównuję z bazą…";
  try {
    const r = await api("/api/analyze", { url, text, tau: tau() });
    analysisId = r.id;
    joined = r.joins;
    showResult(r);
    msg.className = "message";
    msg.textContent = "";
    loadGroups();
    $("result").scrollIntoView({ behavior: smooth() });
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

$("show-groups-btn").addEventListener("click", () => {
  showTab("grupy");
  const hit = document.querySelector(".group.hit");
  (hit || $("panel-grupy")).scrollIntoView({ behavior: smooth() });
});

$("tau").addEventListener("input", () => { $("tau-out").textContent = tau().toFixed(2); });
$("tau").addEventListener("change", () => { joined = []; loadGroups(); });

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const parts = [el("b", { text: casesPl(s.cases) }), " w bazie · "];
    parts.push(s.llm ? "LLM gotowy" : el("span", { class: "warn", text: "brak klucza LLM" }));
    $("status").replaceChildren(...parts);
    $("analyse-btn").disabled = !s.llm;
  } catch (e) {
    $("status").textContent = "serwer nie odpowiada";
  }
}

showTab(location.hash === "#grupy" ? "grupy" : "analizator");
loadStatus();
loadGroups();
