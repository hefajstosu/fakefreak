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

// ---------------------------------------------------------------- labels for the explanations (see ads/explain.py)
const GROUP = {  // feature group -> [label, colour]
  infrastructure: ["Infrastruktura", "#b42318"], core: ["Typ oszustwa i temat", "#1c4f8a"],
  templates: ["Szablony i lejek", "#6b4fa0"], persuasion: ["Techniki perswazji", "#9a5b00"],
  entities: ["Produkt, osoby, firmy, media", "#17643a"], text: ["Narracja i tekst", "#2f7f95"],
  surface: ["Rekwizyty, kwoty, miejsca", "#7d848c"], other: ["Inne", "#aab1b8"],
};
const FEATURE = {
  tracker_ids: "Identyfikatory trackerów", redirect_chain_domains: "Domeny przekierowań",
  dom_and_form_clues: "Endpointy, formularze, pliki", ad_library_page_name: "Strona sponsorująca",
  scam_type: "Typ oszustwa", topic: "Temat", ad_creative_template: "Szablon reklamy",
  landing_page_template: "Szablon strony docelowej", funnel_stages: "Etapy lejka", persuasion_devices: "Techniki perswazji",
  product_name: "Produkt / platforma", featured_people: "Osoby", companies: "Firmy i instytucje",
  impersonated_media: "Podszywane media", narrative: "Schemat narracji", promise: "Obietnica i mechanizm",
  call_to_action: "Wezwanie do działania", embedding: "Streszczenie porównawcze", keywords: "Słowa kluczowe",
  setting_and_props: "Sceneria i rekwizyty", amounts_dates_locations: "Kwoty, daty, miejsca",
  page_structure: "Szkielet strony (HTML, klasy CSS)", page_assets: "Zestaw obrazów strony",
  url_template: "Szablon śledzenia w adresach URL", logos_and_badges: "Logotypy i oznaczenia",
};
const EVIDENCE = {
  tracker: "wspólny identyfikator trackera", endpoint: "wspólne endpointy platformy (sesja/formularz)",
  file: "wspólny charakterystyczny plik strony", domain: "wspólna domena", page: "ta sama strona sponsorująca",
  images: "wspólne identyczne obrazy strony (ten sam zestaw)", adid: "ten sam identyfikator kampanii reklamowej",
  tracking: "ten sam własny szablon parametrów śledzenia", other: "dowód",
};
const MISSING = { a: "brak danych po stronie A", b: "brak danych po stronie B", both: "brak danych po obu stronach",
  unknown: "nie do porównania", supporting: "różne, ale to cecha wspierająca: różnica nie obniża wyniku" };
const ENUM_FEATURES = new Set(["scam_type", "topic", "ad_creative_template", "landing_page_template", "persuasion_devices", "funnel_stages"]);

const $ = (id) => document.getElementById(id);
const f2 = (x) => (x == null ? "–" : Number(x).toFixed(2));
const pretty = (v) => (v == null ? "–" : SCAM[v] || String(v).replaceAll("_", " "));
const evText = (e) => `${EVIDENCE[e.kind] || e.kind}: ${e.value}`;
const RAW_EVIDENCE = [["shared tracker ID", "tracker"], ["shared session/form endpoint", "endpoint"], ["shared page images", "images"],
  ["same ad campaign ID", "adid"], ["same tracking template", "tracking"],
  ["shared distinctive script/style file", "file"], ["shared domain", "domain"], ["same sponsoring page", "page"]];
const evRaw = (s) => {  // a strong_links string from the API -> Polish
  const hit = RAW_EVIDENCE.find(([prefix]) => s.startsWith(prefix));
  return hit ? evText({ kind: hit[1], value: s.slice(hit[0].length + 2) }) : s;
};
let analysisId = null;
let joined = [];
let lastResult = null;
let lastInput = "";

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
const TABS = { analizator: ["tab-analiza", "panel-analiza"], grupy: ["tab-grupy", "panel-grupy"], graf: ["tab-graf", "panel-graf"] };
const ORDER = Object.keys(TABS);

function showTab(name, focus = false) {
  for (const [key, [tabId, panelId]] of Object.entries(TABS)) {
    const on = key === name;
    $(tabId).setAttribute("aria-selected", String(on));
    $(tabId).tabIndex = on ? 0 : -1;
    $(panelId).hidden = !on;
  }
  if (focus) $(TABS[name][0]).focus();
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "graf") loadGraph();
}

for (const [key, [tabId]] of Object.entries(TABS)) {
  $(tabId).addEventListener("click", () => showTab(key));
  $(tabId).addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
      ev.preventDefault();
      const step = ev.key === "ArrowRight" ? 1 : ORDER.length - 1;
      showTab(ORDER[(ORDER.indexOf(key) + step) % ORDER.length], true);
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

// ---------------------------------------------------------------- why two cases are linked (explain.pair)
function chips(items, cls = "tag") {
  return el("span", { class: "tags inline" }, items.map((t) => el("span", { class: cls, text: t })));
}

function valueText(feature, v) {
  return ENUM_FEATURES.has(feature) ? pretty(v) : String(v);
}

const clipText = (t, n = 80) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
const listText = (items, n = 6) => items.slice(0, n).map((x) => clipText(String(x))).join(", ") + (items.length > n ? ` (+${items.length - n})` : "");

function fingerprintText(f) {  // page fingerprints are numbers and hashes: describe them instead of listing them
  const v = f.values || {};
  if ("shared_count" in v) return `${v.shared_count} identycznych obrazów (strony: ${v.images_a} i ${v.images_b} obrazów)`;
  if ("pages_a" in v) return `podobieństwo szkieletu najbliższych stron ${Math.round((f.similarity || 0) * 100)}% (stron: ${v.pages_a} i ${v.pages_b})`;
  return null;
}

function sharedText(f) {  // the same content as sharedOf(), as plain text for the report
  const v = f.values || {};
  if (fingerprintText(f)) return fingerprintText(f);
  if (v.shared_words) return listText(v.shared_words, 10) || "brak wspólnych słów";
  if (v.shared) return listText(v.shared.map((m) => (m.a === m.b ? valueText(f.feature, m.a) : `${m.a} ≈ ${m.b}`))) || "nic wspólnego";
  if ("a" in v) return valueText(f.feature, v.a);
  return "";
}

function sharedOf(f) {
  const v = f.values || {};
  if (fingerprintText(f)) return el("span", {}, fingerprintText(f));
  if (v.shared_words) return v.shared_words.length ? chips(v.shared_words.slice(0, 14)) : el("span", { class: "none", text: "brak wspólnych słów" });
  if (v.shared) {
    if (!v.shared.length) return el("span", { class: "none", text: "nic wspólnego" });
    return chips(v.shared.map((m) => (m.a === m.b ? valueText(f.feature, m.a) : `${m.a} ≈ ${m.b} (${f2(m.similarity)})`)));
  }
  if ("a" in v) return el("span", {}, valueText(f.feature, v.a) + (v.a === v.b ? "" : ` · ${valueText(f.feature, v.b)}`));
  return null;
}

function differenceOf(f, nameA, nameB) {
  const v = f.values || {};
  if (fingerprintText(f)) return el("span", {}, fingerprintText(f));
  const side = (label, items) => el("div", { class: "side" }, [el("span", { class: "who", text: label }),
    items.length ? chips(items.slice(0, 8).map((x) => clipText(valueText(f.feature, x), 90)).concat(items.length > 8 ? [`+${items.length - 8}`] : []), "tag muted")
      : el("span", { class: "none", text: "–" })]);
  if (v.shared || v.shared_words) {
    if (v.shared_words) {
      return el("details", { class: "texts" }, [el("summary", { text: "pokaż oba teksty" }),
        el("p", {}, [el("b", { text: `${nameA}: ` }), v.a || "–"]), el("p", {}, [el("b", { text: `${nameB}: ` }), v.b || "–"])]);
    }
    return el("div", { class: "sides" }, [side(nameA, v.only_a || []), side(nameB, v.only_b || [])]);
  }
  return el("div", { class: "sides" }, [side(nameA, v.a == null ? [] : [v.a]), side(nameB, v.b == null ? [] : [v.b])]);
}

function stackBar(ex) {
  const bar = el("div", { class: "stack", role: "img",
    "aria-label": `Wynik ${f2(ex.score)}: ` + ex.groups.map((g) => `${GROUP[g.group][0]} ${f2(g.contribution)}`).join(", ") });
  for (const g of ex.groups) {
    if (g.contribution <= 0) continue;
    bar.append(el("i", { style: `width:${(g.contribution * 100).toFixed(1)}%;background:${GROUP[g.group][1]}`,
      title: `${GROUP[g.group][0]}: +${f2(g.contribution)}` }));
  }
  if (ex.tau != null) bar.append(el("b", { class: "tau-mark", style: `left:${ex.tau * 100}%`, title: `próg τ = ${f2(ex.tau)}` }));
  return bar;
}

function pairView(ex, nameA, nameB) {
  const tau = ex.tau;
  const verdict = ex.must_link ? "twardy dowód łączy te sprawy niezależnie od wyniku"
    : tau == null ? "" : ex.score >= tau ? `wynik ≥ τ = ${f2(tau)}` : `wynik < τ = ${f2(tau)} (brakuje ${f2(tau - ex.score)})`;
  const head = el("div", { class: "ex-head" }, [
    el("strong", { text: `${nameA} ↔ ${nameB}` }), el("span", { class: "ex-score", text: f2(ex.score) }),
    verdict ? el("span", { class: ex.must_link ? "tag ev-tag" : "tag", text: verdict }) : null,
  ]);
  const legend = el("table", { class: "mini" }, [
    el("thead", {}, el("tr", {}, ["Grupa cech", "Wkład", "Podobieństwo", "Wynik bez tej grupy"].map((t) => el("th", { scope: "col", text: t })))),
    el("tbody", {}, ex.groups.map((g) => el("tr", {}, [
      el("td", {}, [el("span", { class: "sw", style: `background:${GROUP[g.group][1]}` }), GROUP[g.group][0]]),
      el("td", { class: "num", text: `+${f2(g.contribution)}` }),
      el("td", { class: "num", text: `${Math.round((g.similarity || 0) * 100)}%` }),
      el("td", { class: "num" }, [f2(g.without), g.crosses_tau ? el("span", { class: "tag flag", text: g.without < tau ? "spada poniżej τ" : "przekracza τ" }) : null]),
    ]))),
  ]);
  const evidence = ex.evidence.length ? el("div", { class: "ex-sec" }, [el("h5", { text: "Twarde dowody" }),
    el("ul", { class: "ev-list" }, ex.evidence.map((e) => el("li", {}, [evText(e),
      el("span", { class: "tag " + (e.must_link || e.family_link ? "ev-tag" : ""),
        text: e.must_link ? "łączy w kampanię" : e.family_link ? "łączy w rodzinę" : "wspierający" })])))]) : null;
  const counted = ex.features.filter((f) => f.contribution != null);
  const shared = counted.filter((f) => f.contribution > 0);
  const lost = counted.filter((f) => (f.loss || 0) >= 0.015).sort((x, y) => y.loss - x.loss);
  const missing = ex.features.filter((f) => f.contribution == null && f.missing && f.missing !== "both");
  const info = ex.features.filter((f) => f.informative);
  const row = (f, cells) => el("tr", {}, [el("th", { scope: "row" }, [el("span", { class: "sw", style: `background:${GROUP[f.group][1]}` }), FEATURE[f.feature] || f.feature]), ...cells]);
  return el("div", { class: "explain" }, [
    head, stackBar(ex),
    el("p", { class: "hint", text: "Wynik to średnia ważona podobieństw cech dostępnych po obu stronach. Segmenty paska to wkłady grup cech; sumują się do wyniku. Pionowa kreska to próg τ." }),
    el("div", { class: "table-wrap" }, legend),
    evidence,
    el("div", { class: "ex-sec" }, [el("h5", { text: "Co jest wspólne (podnosi wynik)" }),
      el("div", { class: "table-wrap" }, el("table", { class: "mini feats" }, [
        el("thead", {}, el("tr", {}, ["Cecha", "Podob.", "Wkład", "Wspólne wartości"].map((t) => el("th", { scope: "col", text: t })))),
        el("tbody", {}, shared.map((f) => row(f, [el("td", { class: "num", text: `${Math.round(f.similarity * 100)}%` }),
          el("td", { class: "num", text: `+${f2(f.contribution)}` }), el("td", {}, sharedOf(f))]))),
      ]))]),
    lost.length ? el("div", { class: "ex-sec" }, [el("h5", { text: "Co się różni (obniża wynik)" }),
      el("div", { class: "table-wrap" }, el("table", { class: "mini feats" }, [
        el("thead", {}, el("tr", {}, ["Cecha", "Podob.", "Strata", "Różnice"].map((t) => el("th", { scope: "col", text: t })))),
        el("tbody", {}, lost.map((f) => row(f, [el("td", { class: "num", text: `${Math.round(f.similarity * 100)}%` }),
          el("td", { class: "num", text: `−${f2(f.loss)}` }), el("td", {}, differenceOf(f, nameA, nameB))]))),
      ]))]) : null,
    info.length ? el("div", { class: "ex-sec" }, [el("h5", { text: "Poza wynikiem (tylko informacyjnie)" }),
      chips(info.map((f) => `${FEATURE[f.feature] || f.feature}: ${sharedText(f)}`), "tag muted")]) : null,
    missing.length ? el("div", { class: "ex-sec" }, [el("h5", { text: "Pominięte (nie liczone jako różnica)" }),
      chips(missing.map((f) => `${FEATURE[f.feature] || f.feature}: ${MISSING[f.missing]}`), "tag muted")]) : null,
    el("p", { class: "hint", text: "Demografia osób niezidentyfikowanych nigdy nie wpływa na wynik." }),
  ]);
}

async function showPair(target, codeEl, block, a, b, nameA, nameB, extra = "") {
  block.hidden = false;
  codeEl.textContent = `${a} ↔ ${b}`;
  target.replaceChildren(el("p", { class: "hint", text: "Liczę uzasadnienie…" }));
  try {
    const ex = await api(`/api/explain?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&tau=${tau()}${extra}`);
    target.replaceChildren(pairView(ex, nameA, nameB));
  } catch (e) {
    target.replaceChildren(el("p", { class: "message error", text: e.message }));
  }
  block.scrollIntoView({ behavior: smooth(), block: "start" });
}

// ---------------------------------------------------------------- groups tab
let groupNo = new Map();  // sorted member ids -> K number, from the last groups load
const keyOf = (ids) => [...ids].sort().join("|");

const RULE = {
  "single case": () => "Pojedyncza sprawa: nic w bazie nie łączy się z nią twardym dowodem ani średnim podobieństwem ≥ τ.",
  "hard evidence": () => "Wszystkie sprawy łączą twarde dowody (wspólny tracker lub strona sponsorująca). Taki dowód łączy sprawy niezależnie od podobieństwa treści.",
  "same content": () => "Sprawy mają prawie identyczną treść (wynik pary ≥ 0.80): to ta sama reklama z podmienionymi szczegółami. Takie powiązanie łączy niezależnie od reszty kampanii.",
  "hard evidence and same content": () => "Sprawy łączą twarde dowody albo prawie identyczna treść (wynik pary ≥ 0.80); takie powiązania łączą niezależnie od reszty kampanii.",
  "hard evidence and mean score": (x) => `Części ${x.parts.map((p) => `[${p.join(", ")}]`).join(" i ")} łączą twarde dowody lub prawie identyczna treść; części scalono, bo średnie podobieństwo między nimi (${f2(x.parts_mean)}) osiąga τ.`,
  "mean score": (x) => `Brak twardych dowodów; sprawy połączono, bo średnie podobieństwo między nimi (${f2(x.parts_mean)}) osiąga τ.`,
};

function campaignWhy(g) {
  const x = g.explanation;
  if (!x) return null;
  const items = [el("p", { text: (RULE[x.rule] || (() => x.rule))(x) })];
  if (x.cohesion) {
    items.push(el("p", { class: "hint", text: `Spójność: najsłabsza para ${f2(x.cohesion.min)} · średnio ${f2(x.cohesion.mean)} · najsilniejsza ${f2(x.cohesion.max)}.` +
      (x.weakest ? ` Najsłabiej związana: sprawa ${x.weakest.case} (średnio ${f2(x.weakest.mean)} z pozostałymi).` : "") }));
  }
  if (x.signature.length) {
    const byFeature = new Map();
    for (const s of x.signature) {
      if (!byFeature.has(s.feature)) byFeature.set(s.feature, []);
      byFeature.get(s.feature).push(s);
    }
    items.push(el("div", { class: "sig" }, [el("h5", { text: "Wspólna sygnatura (wartości w co najmniej połowie spraw)" }),
      el("dl", { class: "fields sig-list" }, [...byFeature].flatMap(([feat, vals]) => [
        el("dt", { text: FEATURE[feat] || feat }),
        el("dd", {}, chips(vals.slice(0, 10).map((v) => `${valueText(feat, v.value)} · ${v.count}/${v.of}`), v_cls(feat))),
      ]))]));
  }
  if (x.nearest) {
    const n = x.nearest;
    const no = groupNo.get(keyOf(n.members));
    items.push(el("p", { class: "sep", text: `Najbliższa inna kampania: ${no ? `K${no}` : ""} (${n.members.join(", ")}) – średnie podobieństwo ${f2(n.mean)} ` +
      (n.mean < g_tau() ? `< τ ${f2(g_tau())} (brakuje ${f2(n.gap)})` : `≥ τ`) +
      `, najlepsza para ${n.best_pair.a}–${n.best_pair.b}: ${f2(n.best_pair.score)}` +
      (n.hard_evidence ? "." : n.family_evidence
        ? ". Łączy je wspólne narzędzie do stron (ta sama rodzina), ale nie dowód jednego operatora. Dlatego osobna kampania w tej samej rodzinie."
        : ", brak twardego dowodu. Dlatego osobna kampania.") }));
  }
  return el("div", { class: "why-box" }, [el("h5", { text: "Dlaczego te sprawy są razem" }), ...items]);
}

const v_cls = (feat) => (["tracker_ids", "redirect_chain_domains", "dom_and_form_clues"].includes(feat) ? "tag ev-tag" : "tag");
let lastGroupsTau = 0.6;
const g_tau = () => lastGroupsTau;

async function loadGroups() {
  const box = $("groups");
  try {
    const data = await api(`/api/groups?tau=${tau()}`);
    lastGroupsTau = data.tau;
    groupNo = new Map(data.groups.map((g) => [keyOf(g.members.map((m) => m.case)), g.no]));
    $("groups-hint").textContent = `Kampania: sprawy połączone twardym dowodem (tracker, strona sponsorująca), prawie identyczną treścią albo średnim podobieństwem ≥ τ = ${data.tau.toFixed(2)}. ` +
      "Rodzina: kampanie z tym samym typem oszustwa i wynikiem ≥ 0.30 albo wspólnym narzędziem do stron.";
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
  const links = g.links.slice(0, 8).map((l) => {
    const detail = el("div", { class: "link-detail", hidden: "" });
    const btn = el("button", { type: "button", class: "link-btn why", "aria-expanded": "false", text: "Dlaczego?" });
    btn.addEventListener("click", async () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      detail.hidden = !open;
      if (open && !detail.childElementCount) {
        detail.append(el("p", { class: "hint", text: "Liczę uzasadnienie…" }));
        try {
          const ex = await api(`/api/explain?a=${encodeURIComponent(l.a)}&b=${encodeURIComponent(l.b)}&tau=${tau()}`);
          detail.replaceChildren(pairView(ex, `Sprawa ${l.a}`, `Sprawa ${l.b}`));
        } catch (e) {
          detail.replaceChildren(el("p", { class: "message error", text: e.message }));
        }
      }
    });
    return el("li", {}, [
      el("span", { class: "pair", text: `${l.a} ↔ ${l.b}` }),
      el("span", { class: "sc", text: l.score.toFixed(2) }),
      l.evidence.length ? el("span", { class: "ev", text: l.evidence.map(evRaw).join("; ") }) : el("span", { class: "none", text: "brak twardych dowodów" }),
      btn, detail,
    ]);
  });
  const body = el("div", { class: "group-body" }, [
    campaignWhy(g),
    links.length ? el("ul", { class: "links", "aria-label": "Powiązania między sprawami" }, links) : null,
    el("div", { class: "cases" }, g.members.map((m) => caseCard(m, `Sprawa ${m.case}`))),
  ]);
  const row = el("details", { class: "group" + (hit ? " hit" : "") }, [summary, body]);
  row.open = hit;
  return row;
}

// ---------------------------------------------------------------- why this verdict (explain.decision_reasons)
function reasonLines(r) {
  const x = r.reasons, t = x.thresholds, s = f2(x.top_score), c = x.top_case;
  const ev = (list) => list.map(evText).join("; ");
  const lines = [];
  const dup = x.duplicates[0];
  switch (x.rule) {
    case "capture":
      lines.push(`Ten sam materiał co sprawa ${dup.case}: ${dup.reasons.join("; ")}. Dołączony do tamtego wpisu, nie liczony jako nowy.`);
      break;
    case "content":
      lines.push(`Ta sama treść co sprawa ${dup.case} (${dup.reasons.join("; ")}), ale inne ślady techniczne: typowe dla jednej kampanii przeniesionej na nowe domeny.`);
      break;
    case "empty":
      lines.push("Baza jest pusta, więc nie ma z czym porównać.");
      break;
    case "score_confirm":
      lines.push(`Najbliższa sprawa ${c}: wynik ${s} ≥ ${f2(t.confirm)} (próg potwierdzenia bez twardego dowodu).`);
      break;
    case "tau_and_evidence":
      lines.push(`Najbliższa sprawa ${c}: wynik ${s} ≥ τ = ${f2(t.tau)} i twardy dowód: ${ev(x.evidence)}.`);
      break;
    case "hard_evidence":
      lines.push(`Twardy dowód ze sprawą ${x.hard_case}: ${ev(x.hard_evidence)}. Taki dowód łączy z kampanią niezależnie od podobieństwa treści (tu ${f2(x.hard_score)}; τ = ${f2(t.tau)}).`);
      if (c !== x.hard_case) lines.push(`Najbliższa sprawa pod względem treści to ${c} (${s}); tabela niżej pokazuje, do której kampanii należy.`);
      break;
    case "tau_only":
      lines.push(`Najbliższa sprawa ${c}: wynik ${s} ≥ τ = ${f2(t.tau)}, ale bez twardego dowodu (tracker, domena, endpointy platformy). Potrzebne potwierdzenie analityka.`);
      break;
    case "family_evidence":
      lines.push(`Wspólne endpointy platformy ze sprawą ${x.family_case}: ${ev(x.family_evidence)}. To samo narzędzie do stron i ten sam typ oszustwa, więc ta sama rodzina kampanii; narzędzia może używać kilku operatorów, a wynik treści (${f2(x.family_score)}) jest za niski, by uznać to za tę samą kampanię.`);
      break;
    case "family":
      lines.push(`Najbliższa sprawa ${c}: wynik ${s} < τ = ${f2(t.tau)}, ale ≥ ${f2(t.family)} (próg rodziny). Materiał przypomina znaną rodzinę oszustw, za mało na tę samą kampanię (tak wygląda np. sama reklama bez strony docelowej).`);
      break;
    case "nothing":
      lines.push(`Najbliższa sprawa ${c}: wynik ${s} < ${f2(t.family)} (próg rodziny). Nic w bazie nie jest blisko: kandydat na nową kampanię.`);
      break;
    default:
      lines.push(`${r.decision.title}. ${r.decision.explanation}`);
  }
  const top = r.neighbours[0];
  if (top && top.explanation && !["capture", "content", "hard_evidence"].includes(x.rule)) {
    const ex = top.explanation;
    const main = [...ex.groups].sort((p, q) => q.contribution - p.contribution)[0];
    if (main) lines.push(`Do wyniku ze sprawą ${top.case} najwięcej wnosi grupa „${GROUP[main.group][0]}” (+${f2(main.contribution)}); bez niej wynik wyniósłby ${f2(main.without)}.`);
    const crossing = ex.groups.filter((g) => g.crosses_tau);
    lines.push(crossing.length
      ? `Decyzja zależy od grup: ${crossing.map((g) => `„${GROUP[g.group][0]}”`).join(", ")}. Bez którejkolwiek z nich wynik znalazłby się po drugiej stronie progu τ.`
      : "Żadna pojedyncza grupa cech nie przesuwa wyniku przez próg τ: decyzja jest stabilna.");
  }
  lines.push(`Progi: τ = ${f2(t.tau)} (kampania), ${f2(t.family)} (rodzina), ${f2(t.confirm)} (potwierdzenie bez twardego dowodu).`);
  return lines;
}

function hardSummary(row) {  // "sprawy 1, 2: <evidence>" with one line per distinct piece of evidence
  const by = new Map();
  for (const h of row.hard) for (const e of h.evidence.filter((x) => x.must_link)) {
    const k = evText(e);
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(h.case);
  }
  return [...by].map(([ev, cases]) => `${cases.length > 1 ? "sprawy" : "sprawa"} ${cases.join(", ")}: ${ev}`);
}

function campaignResult(row) {
  if (row.joined) {
    if (row.rule === "hard evidence") return "dołączono: twardy dowód";
    if (row.rule === "same content") return `dołączono: prawie ta sama treść co sprawa ${row.best.case} (${f2(row.best.score)} ≥ ${f2(lastResult?.thresholds?.confirm ?? 0.8)})`;
    return "dołączono: średnia ≥ τ";
  }
  return `nie dołączono: brakuje ${f2(row.gap)} do τ (najbliższa sprawa ${row.best.case}: ${f2(row.best.score)})`;
}

function campaignRows(r) {
  return r.campaigns.map((row) => {
    const meter = el("span", { class: "meter", "aria-hidden": "true" }, [
      el("i", { style: `width:${Math.round(row.mean * 100)}%` }),
      el("b", { class: "tau-mark", style: `left:${r.thresholds.tau * 100}%` }),
    ]);
    const hard = hardSummary(row);
    return el("tr", { class: row.joined ? "joined" : null }, [
      el("td", {}, [el("b", { class: "case-link", text: row.no ? `K${row.no}` : "–" }), el("span", { class: "hint", text: ` ${row.members.join(", ")}` })]),
      el("td", { class: "num" }, [meter, f2(row.mean)]),
      el("td", { class: hard.length ? "ev" : null, text: hard.join("; ") || "–" }),
      el("td", { text: campaignResult(row) }),
    ]);
  });
}

function familyText(r) {
  const joined = (r.families || []).filter((f) => f.joined);
  if (!joined.length) {
    return `Rodzina kampanii: żadna. Brak sprawy tego samego typu oszustwa z wynikiem ≥ ${f2(r.thresholds.family)} i brak wspólnego narzędzia do stron.`;
  }
  return joined.map((f) => {
    const why = [];
    if (f.evidence_with.length) why.push(`wspólne endpointy platformy ze sprawą ${f.evidence_with.join(", ")}`);
    if (f.score_with.length) why.push(`wynik ≥ ${f2(r.thresholds.family)} i ten sam typ oszustwa ze sprawą ${f.score_with.join(", ")}`);
    return `Rodzina kampanii (sprawy ${f.members.join(", ")}): dołączono, bo ${why.join("; ")}.`;
  }).join(" ");
}

function showNeighbourWhy(n) {
  $("pair-block").hidden = false;
  $("pair-code").textContent = `nowy ↔ ${n.case}`;
  $("pair-detail").replaceChildren(pairView(n.explanation, "Analizowany artykuł", `Sprawa ${n.case}`));
  $("pair-block").scrollIntoView({ behavior: smooth(), block: "start" });
}

// ---------------------------------------------------------------- report (Markdown, built from the same data as the page)
function reportMarkdown(r) {
  const md = [];
  const [, stamp, heading] = STATUS[r.decision.status] || ["", r.decision.status, r.decision.status];
  const p = r.profile;
  md.push("# Raport analizy artykułu", "", `Data: ${new Date().toLocaleString("pl-PL")}  `, `Źródło: ${lastInput || "wklejony tekst"}  `,
    `Próg τ: ${f2(r.thresholds.tau)}`, "", "## Werdykt", "", `**${stamp}**: ${heading}`, "", ...reasonLines(r).map((l) => `- ${l}`), "");
  md.push("## Dopasowanie do kampanii", "", "| Kampania | Sprawy | Średnie podobieństwo | Twardy dowód | Wynik |", "|---|---|---|---|---|");
  for (const row of r.campaigns) {
    const hard = hardSummary(row).join("; ") || "–";
    md.push(`| ${row.no ? `K${row.no}` : "–"} | ${row.members.join(", ")} | ${f2(row.mean)} | ${hard} | ${campaignResult(row)} |`);
  }
  md.push("", familyText(r), "", "## Najbliższe sprawy i uzasadnienie", "");
  for (const n of r.neighbours) {
    const ex = n.explanation;
    md.push(`### Sprawa ${n.case}: wynik ${f2(ex.score)}${ex.must_link ? " (twardy dowód)" : ""}`, "");
    for (const e of ex.evidence) md.push(`- Dowód: ${evText(e)} (${e.must_link ? "łączy w kampanię" : e.family_link ? "łączy w rodzinę" : "wspierający"})`);
    md.push("", "| Grupa cech | Wkład | Podobieństwo | Wynik bez tej grupy |", "|---|---|---|---|");
    for (const g of ex.groups) md.push(`| ${GROUP[g.group][0]} | +${f2(g.contribution)} | ${Math.round((g.similarity || 0) * 100)}% | ${f2(g.without)}${g.crosses_tau ? " (zmienia stronę progu)" : ""} |`);
    const shared = ex.features.filter((f) => (f.contribution || 0) > 0).slice(0, 8);
    md.push("", "Wspólne:");
    for (const f of shared) md.push(`- ${FEATURE[f.feature] || f.feature} (${Math.round(f.similarity * 100)}%, +${f2(f.contribution)}): ${sharedText(f)}`);
    const lost = ex.features.filter((f) => (f.loss || 0) >= 0.015).sort((x, y) => y.loss - x.loss).slice(0, 5);
    if (lost.length) {
      md.push("", "Różnice:");
      for (const f of lost) {
        const v = f.values || {};
        const diff = v.only_a ? `tylko artykuł: ${listText(v.only_a) || "–"}; tylko sprawa: ${listText(v.only_b) || "–"}`
          : v.shared_words ? "inne sformułowania" : `${pretty(v.a)} / ${pretty(v.b)}`;
        md.push(`- ${FEATURE[f.feature] || f.feature} (−${f2(f.loss)}): ${diff}`);
      }
    }
    const missing = ex.features.filter((f) => f.contribution == null && f.missing && f.missing !== "both");
    if (missing.length) md.push("", `Pominięte z braku danych: ${missing.map((f) => FEATURE[f.feature] || f.feature).join(", ")}`);
    md.push("");
  }
  md.push("## Profil artykułu (LLM)", "", `- Typ: ${pretty(p.scam_type)} · ${p.topic}`, `- Produkt: ${p.product || "–"}`,
    `- Osoby: ${p.people.join(", ") || "–"}`, `- Podszywa się: ${p.media.join(", ") || "–"}`, `- Szablon: ${p.templates}`,
    `- Domeny: ${p.domains.join(", ") || "–"}`, `- Techniki perswazji: ${p.persuasion.map(pretty).join(", ") || "–"}`, "", p.summary || "", "",
    "---", "Wynik = średnia ważona podobieństw cech dostępnych po obu stronach; wkłady grup sumują się do wyniku. " +
    "Twardy dowód (wspólny tracker, endpointy platformy, strona sponsorująca) łączy sprawy niezależnie od wyniku. " +
    "Demografia osób niezidentyfikowanych nie wpływa na wynik. Raport zawiera dane z materiałów: nie publikować.");
  return md.join("\n");
}

function downloadReport() {
  if (!lastResult) return;
  const blob = new Blob([reportMarkdown(lastResult)], { type: "text/markdown;charset=utf-8" });
  const a = el("a", { href: URL.createObjectURL(blob), download: `raport-${lastResult.decision.status}-${Date.now()}.md` });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

// ---------------------------------------------------------------- graph tab: cases, campaigns, families and links
const SVG = "http://www.w3.org/2000/svg";
const PALETTE = ["#1c4f8a", "#17643a", "#9a5b00", "#6b4fa0", "#2f7f95", "#8a3b12", "#4d5a1e", "#7a2e5c"];
let graphTau = null;

function svg(tag, attrs = {}, children = []) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
  for (const c of [].concat(children)) if (c != null) node.append(c);
  return node;
}

function layout(nodes) {
  // campaigns of one family side by side; members on a circle around the campaign centre; rows wrap at W
  const W = 960, GAP = 34, NODE = 17;
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
    const cx = x + size / 2, cy = y + size / 2;
    c.members.forEach((m, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / k;
      pos.set(m.case, [cx + r * Math.cos(a), cy + r * Math.sin(a)]);
    });
    boxes.push({ c, x, y, size });
    const f = famBox.get(c.family) || { x0: x, y0: y, x1: x + size, y1: y + size, n: 0 };
    famBox.set(c.family, { x0: Math.min(f.x0, x), y0: Math.min(f.y0, y), x1: Math.max(f.x1, x + size), y1: Math.max(f.y1, y + size), n: f.n + 1 });
    x += size + GAP;
    used = Math.max(used, x);
    rowH = Math.max(rowH, size);
  }
  // a small database is drawn larger, but never wider than 2.2x the full layout scale
  return { pos, boxes, famBox, width: Math.max(used, W / 2.2), height: y + rowH + GAP, NODE };
}

async function loadGraph() {
  if (graphTau === tau()) return;
  const box = $("graph");
  box.replaceChildren(el("p", { class: "hint", text: "Rysuję graf…" }));
  try {
    const g = await api(`/api/graph?tau=${tau()}`);
    graphTau = g.tau;
    drawGraph(g);
  } catch (e) {
    box.replaceChildren(el("p", { class: "message error", text: `Nie udało się wczytać grafu: ${e.message}` }));
  }
}

function edgeClass(e) {
  return e.must_link ? "hard" : e.same_campaign ? "same" : e.family_link ? "famev" : "fam";
}

function openEdge(e) {
  showPair($("graph-pair-detail"), $("graph-pair-code"), $("graph-pair"), e.a, e.b, `Sprawa ${e.a}`, `Sprawa ${e.b}`);
}

function drawGraph(g) {
  $("graph-hint").textContent = `τ = ${f2(g.tau)}. Krawędzie: każda para z twardym dowodem oraz do 4 najsilniejszych powiązań każdej sprawy z wynikiem ≥ ${f2(g.family_score)} (próg rodziny).`;
  if (!g.nodes.length) {
    $("graph").replaceChildren(el("p", { class: "hint", text: "Baza jest pusta." }));
    return;
  }
  const L = layout(g.nodes);
  const colour = (no, size) => (size > 1 ? PALETTE[(no - 1) % PALETTE.length] : "#ffffff");
  const sizes = new Map();
  for (const n of g.nodes) sizes.set(n.campaign, (sizes.get(n.campaign) || 0) + 1);
  const root = svg("svg", { viewBox: `0 0 ${L.width} ${L.height}`, class: "graph-svg", role: "group", "aria-label": "Graf powiązań między sprawami" });
  for (const [fam, f] of L.famBox) {
    if (f.n < 2) continue;
    root.append(svg("rect", { x: f.x0 - 10, y: f.y0 - 10, width: f.x1 - f.x0 + 20, height: f.y1 - f.y0 + 20, class: "fam-box" }),
      svg("text", { x: f.x0 - 4, y: f.y0 - 14, class: "fam-label" }, `rodzina ${fam}`));
  }
  for (const b of L.boxes) {
    if (b.c.members.length > 1) root.append(svg("text", { x: b.x + 2, y: b.y + 8, class: "camp-label" }, `K${b.c.no}`));
  }
  for (const e of [...g.edges].sort((p, q) => p.score - q.score)) {
    const [x1, y1] = L.pos.get(e.a), [x2, y2] = L.pos.get(e.b);
    const title = svg("title", {}, `${e.a} ↔ ${e.b}: ${f2(e.score)}${e.evidence.length ? " · " + e.evidence.map(evRaw).join("; ") : ""}`);
    const line = svg("line", { x1, y1, x2, y2, class: `edge ${edgeClass(e)}`, "stroke-width": (1 + 5 * e.score).toFixed(1) });
    const hit = svg("line", { x1, y1, x2, y2, class: "edge-hit" }, title);
    hit.addEventListener("click", () => openEdge(e));
    root.append(line, hit);
  }
  for (const n of g.nodes) {
    const [x, y] = L.pos.get(n.case);
    const node = svg("g", { class: "node", tabindex: "0", role: "button", "aria-label": `Sprawa ${n.case}, kampania K${n.campaign}` }, [
      svg("title", {}, `Sprawa ${n.case} · K${n.campaign} · ${pretty(n.scam_type)}${n.product ? " · " + n.product : ""}`),
      svg("circle", { cx: x, cy: y, r: L.NODE, fill: colour(n.campaign, sizes.get(n.campaign)), class: sizes.get(n.campaign) > 1 ? "" : "single" }),
      svg("text", { x, y: y + 4, "text-anchor": "middle", class: sizes.get(n.campaign) > 1 ? "on-dark" : "" }, n.case),
    ]);
    const go = () => openCase(n.case);
    node.addEventListener("click", go);
    node.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(); } });
    root.append(node);
  }
  $("graph").replaceChildren(root);
  $("edge-count").textContent = `[${g.edges.length}]`;
  const kind = { hard: "twardy dowód", same: "ta sama kampania", famev: "wspólne narzędzie, ta sama rodzina", fam: "różne kampanie" };
  $("edge-list").replaceChildren(el("ul", { class: "links" }, [...g.edges].sort((p, q) => q.score - p.score).map((e) => {
    const btn = el("button", { type: "button", class: "link-btn why", text: "Dlaczego?" });
    btn.addEventListener("click", () => openEdge(e));
    return el("li", {}, [
      el("span", { class: "pair", text: `${e.a} ↔ ${e.b}` }), el("span", { class: "sc", text: f2(e.score) }),
      el("span", { class: e.must_link || e.family_link ? "ev" : "none", text: `${kind[edgeClass(e)]}${e.evidence.length ? ": " + e.evidence.map(evRaw).join("; ") : ""}` }),
      btn,
    ]);
  })));
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
    el("p", { text: reasonLines(r)[0] }),
    notes.length ? el("p", { class: "notes", text: `Skan strony: ${notes.join("; ")}` }) : null,
  ].filter(Boolean));
  $("reasons").replaceChildren(el("h5", { text: "Dlaczego taki werdykt: szczegóły" }),
    el("ul", { class: "reason-list" }, reasonLines(r).slice(1).map((l) => el("li", { text: l }))));
  $("campaigns").tBodies[0].replaceChildren(...campaignRows(r));
  $("family-line").textContent = familyText(r);
  $("pair-block").hidden = true;
  $("profile").replaceChildren(caseCard(r.profile, "Analizowany artykuł"));
  $("neighbours").tBodies[0].replaceChildren(...r.neighbours.map((n) => {
    const link = el("a", { href: "#grupy", text: n.case });
    link.addEventListener("click", (ev) => { ev.preventDefault(); openCase(n.case); });
    const meter = el("span", { class: "meter", "aria-hidden": "true" }, el("i", { style: `width:${Math.round(n.score * 100)}%` }));
    const why = el("button", { type: "button", class: "link-btn why", text: "Dlaczego?" });
    why.addEventListener("click", () => showNeighbourWhy(n));
    return el("tr", {}, [
      el("td", {}, link),
      el("td", { class: "num" }, [meter, n.score.toFixed(2)]),
      el("td", { text: n.product || "–" }),
      el("td", { class: n.evidence.length ? "ev" : null, text: n.evidence.map(evRaw).join("; ") || "–" }),
      el("td", {}, why),
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
    lastResult = r;
    lastInput = url;
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
    graphTau = null;
    await Promise.all([loadStatus(), loadGroups()]);
  } catch (e) {
    $("save-msg").textContent = e.message;
    $("save-btn").disabled = false;
  }
});

$("report-btn").addEventListener("click", downloadReport);

$("show-groups-btn").addEventListener("click", () => {
  showTab("grupy");
  const hit = document.querySelector(".group.hit");
  (hit || $("panel-grupy")).scrollIntoView({ behavior: smooth() });
});

$("tau").addEventListener("input", () => { $("tau-out").textContent = tau().toFixed(2); });
$("tau").addEventListener("change", () => {
  joined = [];
  loadGroups();
  if (!$("panel-graf").hidden) loadGraph();
});

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

showTab(ORDER.includes(location.hash.slice(1)) ? location.hash.slice(1) : "analizator");
loadStatus();
loadGroups();
