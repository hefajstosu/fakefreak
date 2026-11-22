// Why two cases are linked (the pair explanation of ads/explain/pair.py).
import { $, api, chips, clipText, el, f2, listText, note, smooth, tau } from "./dom.js";
import { GROUP, MISSING, evText, featureName, infraText, linkKind, valueText } from "./labels.js";

function described(f) {  // features whose values are counts or hashes: a sentence instead of a list
  const v = f.values || {};
  if (f.feature === "infra_metadata") {
    return (v.shared || []).length ? v.shared.map((m) => infraText(m.a)).join("; ")
      : "brak wspólnych faktów, które łączą (partia rejestracji, hosting, certyfikat)";
  }
  if ("shared_count" in v) return `${v.shared_count} identycznych obrazów (strony: ${v.images_a} i ${v.images_b} obrazów)`;
  if ("pages_a" in v) return `podobieństwo szkieletu najbliższych stron ${Math.round((f.similarity || 0) * 100)}% (stron: ${v.pages_a} i ${v.pages_b})`;
  return null;
}

export function sharedText(f) {  // what both cases share, as plain text (report, chips)
  const v = f.values || {};
  if (described(f)) return described(f);
  if (v.shared_words) return listText(v.shared_words, 10) || "brak wspólnych słów";
  if (v.shared) return listText(v.shared.map((m) => (m.a === m.b ? valueText(f.feature, m.a) : `${m.a} ≈ ${m.b}`))) || "nic wspólnego";
  return "a" in v ? valueText(f.feature, v.a) : "";
}

function sharedOf(f) {
  const v = f.values || {};
  if (described(f)) return el("span", { text: described(f) });
  if (v.shared_words) return v.shared_words.length ? chips(v.shared_words.slice(0, 14)) : el("span", { class: "none", text: "brak wspólnych słów" });
  if (v.shared) {
    return v.shared.length ? chips(v.shared.map((m) => (m.a === m.b ? valueText(f.feature, m.a) : `${m.a} ≈ ${m.b} (${f2(m.similarity)})`)))
      : el("span", { class: "none", text: "nic wspólnego" });
  }
  return "a" in v ? el("span", { text: valueText(f.feature, v.a) + (v.a === v.b ? "" : ` · ${valueText(f.feature, v.b)}`) }) : null;
}

function differenceOf(f, nameA, nameB) {
  const v = f.values || {};
  if (described(f)) return el("span", { text: described(f) });
  if (v.shared_words) {
    return el("details", { class: "texts" }, [el("summary", { text: "pokaż oba teksty" }),
      el("p", {}, [el("b", { text: `${nameA}: ` }), v.a || "–"]), el("p", {}, [el("b", { text: `${nameB}: ` }), v.b || "–"])]);
  }
  const side = (label, items) => el("div", { class: "side" }, [el("span", { class: "who", text: label }),
    items.length ? chips(items.slice(0, 8).map((x) => clipText(valueText(f.feature, x), 90)).concat(items.length > 8 ? [`+${items.length - 8}`] : []), "tag muted")
      : el("span", { class: "none", text: "–" })]);
  const [onlyA, onlyB] = v.shared ? [v.only_a || [], v.only_b || []] : [v.a == null ? [] : [v.a], v.b == null ? [] : [v.b]];
  return el("div", { class: "sides" }, [side(nameA, onlyA), side(nameB, onlyB)]);
}

function stackBar(ex) {
  const bar = el("div", { class: "stack", role: "img",
    "aria-label": `Wynik ${f2(ex.score)}: ` + ex.groups.map((g) => `${GROUP[g.group][0]} ${f2(g.contribution)}`).join(", ") });
  for (const g of ex.groups.filter((x) => x.contribution > 0)) {
    bar.append(el("i", { style: `width:${(g.contribution * 100).toFixed(1)}%;background:${GROUP[g.group][1]}`,
      title: `${GROUP[g.group][0]}: +${f2(g.contribution)}` }));
  }
  if (ex.tau != null) bar.append(el("b", { class: "tau-mark", style: `left:${ex.tau * 100}%`, title: `próg τ = ${f2(ex.tau)}` }));
  return bar;
}

const table = (head, rows) => el("div", { class: "table-wrap" }, el("table", { class: "mini feats" }, [
  el("thead", {}, el("tr", {}, head.map((t) => el("th", { scope: "col", text: t })))), el("tbody", {}, rows)]));
const section = (title, ...body) => el("div", { class: "ex-sec" }, [el("h5", { text: title }), ...body]);

export function pairView(ex, nameA, nameB) {
  const t = ex.tau;
  const verdict = ex.must_link ? "twardy dowód łączy te sprawy niezależnie od wyniku"
    : t == null ? "" : ex.score >= t ? `wynik ≥ τ = ${f2(t)}` : `wynik < τ = ${f2(t)} (brakuje ${f2(t - ex.score)})`;
  const groups = el("div", { class: "table-wrap" }, el("table", { class: "mini" }, [
    el("thead", {}, el("tr", {}, ["Grupa cech", "Wkład", "Podobieństwo", "Wynik bez tej grupy"].map((x) => el("th", { scope: "col", text: x })))),
    el("tbody", {}, ex.groups.map((g) => el("tr", {}, [
      el("td", {}, [el("span", { class: "sw", style: `background:${GROUP[g.group][1]}` }), GROUP[g.group][0]]),
      el("td", { class: "num", text: `+${f2(g.contribution)}` }),
      el("td", { class: "num", text: `${Math.round((g.similarity || 0) * 100)}%` }),
      el("td", { class: "num" }, [f2(g.without), g.crosses_tau ? el("span", { class: "tag flag", text: g.without < t ? "spada poniżej τ" : "przekracza τ" }) : null]),
    ]))),
  ]));
  const row = (f, cells) => el("tr", {}, [el("th", { scope: "row" }, [el("span", { class: "sw", style: `background:${GROUP[f.group][1]}` }), featureName(f.feature)]), ...cells]);
  const shared = ex.features.filter((f) => f.contribution > 0);
  const lost = ex.features.filter((f) => (f.loss || 0) >= 0.015).sort((x, y) => y.loss - x.loss);
  const missing = ex.features.filter((f) => f.contribution == null && f.missing && f.missing !== "both");
  const info = ex.features.filter((f) => f.informative);
  return el("div", { class: "explain" }, [
    el("div", { class: "ex-head" }, [el("strong", { text: `${nameA} ↔ ${nameB}` }), el("span", { class: "ex-score", text: f2(ex.score) }),
      verdict ? el("span", { class: ex.must_link ? "tag ev-tag" : "tag", text: verdict }) : null]),
    stackBar(ex),
    note("Wynik to średnia ważona podobieństw cech dostępnych po obu stronach. Segmenty paska to wkłady grup cech; sumują się do wyniku. Pionowa kreska to próg τ."),
    groups,
    ex.evidence.length ? section("Dowody", el("ul", { class: "ev-list" }, ex.evidence.map((e) =>
      el("li", {}, [evText(e), el("span", { class: "tag " + (e.must_link || e.family_link ? "ev-tag" : ""), text: linkKind(e) })])))) : null,
    section("Co jest wspólne (podnosi wynik)", table(["Cecha", "Podob.", "Wkład", "Wspólne wartości"], shared.map((f) => row(f, [
      el("td", { class: "num", text: `${Math.round(f.similarity * 100)}%` }), el("td", { class: "num", text: `+${f2(f.contribution)}` }),
      el("td", {}, sharedOf(f))])))),
    lost.length ? section("Co się różni (obniża wynik)", table(["Cecha", "Podob.", "Strata", "Różnice"], lost.map((f) => row(f, [
      el("td", { class: "num", text: `${Math.round(f.similarity * 100)}%` }), el("td", { class: "num", text: `−${f2(f.loss)}` }),
      el("td", {}, differenceOf(f, nameA, nameB))])))) : null,
    info.length ? section("Poza wynikiem (tylko informacyjnie)", chips(info.map((f) => `${featureName(f.feature)}: ${sharedText(f)}`), "tag muted")) : null,
    missing.length ? section("Pominięte (nie liczone jako różnica)", chips(missing.map((f) => `${featureName(f.feature)}: ${MISSING[f.missing]}`), "tag muted")) : null,
    note("Demografia osób niezidentyfikowanych nigdy nie wpływa na wynik."),
  ]);
}

export async function fetchPair(a, b) {
  return api(`/api/explain?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&tau=${tau()}`);
}

export async function showPair(blockId, a, b) {  // the explanation of two database cases in a block with a code label
  const block = $(blockId);
  const body = block.querySelector(".block-body");
  block.hidden = false;
  block.querySelector(".code").textContent = `${a} ↔ ${b}`;
  body.replaceChildren(note("Liczę uzasadnienie…"));
  try {
    body.replaceChildren(pairView(await fetchPair(a, b), `Sprawa ${a}`, `Sprawa ${b}`));
  } catch (e) {
    body.replaceChildren(note(e.message, "message error"));
  }
  block.scrollIntoView({ behavior: smooth(), block: "start" });
}
