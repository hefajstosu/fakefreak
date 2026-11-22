// The groups tab: campaigns with their explanation (ads/explain/campaign.py), links and case cards.
import { $, api, casesPl, chips, el, f2, note, tau } from "./dom.js";
import { SCAM, evRaw, featureName, valueText } from "./labels.js";
import { keyOf, state } from "./state.js";
import { caseCard } from "./card.js";
import { fetchPair, pairView } from "./explain.js";

const RULE = {
  "single case": () => "Pojedyncza sprawa: nic w bazie nie łączy się z nią twardym dowodem ani średnim podobieństwem ≥ τ.",
  "hard evidence": () => "Wszystkie sprawy łączą twarde dowody (wspólny tracker, strona sponsorująca, identyfikator kampanii reklamowej lub certyfikat). Taki dowód łączy niezależnie od podobieństwa treści.",
  "same content": () => "Sprawy mają prawie identyczną treść (wynik pary ≥ 0.80): to ta sama reklama z podmienionymi szczegółami. Takie powiązanie łączy niezależnie od reszty kampanii.",
  "hard evidence and same content": () => "Sprawy łączą twarde dowody albo prawie identyczna treść (wynik pary ≥ 0.80); takie powiązania łączą niezależnie od reszty kampanii.",
  "hard evidence and mean score": (x) => `Części ${x.parts.map((p) => `[${p.join(", ")}]`).join(" i ")} łączą twarde dowody lub prawie identyczna treść; części scalono, bo średnie podobieństwo między nimi (${f2(x.parts_mean)}) osiąga τ.`,
  "mean score": (x) => `Brak twardych dowodów; sprawy połączono, bo średnie podobieństwo między nimi (${f2(x.parts_mean)}) osiąga τ.`,
};
const TRACES = new Set(["tracker_ids", "redirect_chain_domains", "dom_and_form_clues", "infra_metadata"]);

function separation(n) {
  const no = state.groupNo.get(keyOf(n.members));
  const t = state.groupsTau;
  const why = n.hard_evidence ? "."
    : n.family_evidence ? ". Łączy je dowód rodziny (wspólne narzędzie, zestaw stron lub szablon śledzenia), ale nie dowód jednego operatora. Dlatego osobna kampania w tej samej rodzinie."
      : ", brak twardego dowodu. Dlatego osobna kampania.";
  return `Najbliższa inna kampania: ${no ? `K${no} ` : ""}(${n.members.join(", ")}) – średnie podobieństwo ${f2(n.mean)} ` +
    (n.mean < t ? `< τ ${f2(t)} (brakuje ${f2(n.gap)})` : "≥ τ") + `, najlepsza para ${n.best_pair.a}–${n.best_pair.b}: ${f2(n.best_pair.score)}${why}`;
}

function campaignWhy(x) {
  const items = [el("p", { text: (RULE[x.rule] || (() => x.rule))(x) })];
  if (x.cohesion) {
    items.push(note(`Spójność: najsłabsza para ${f2(x.cohesion.min)} · średnio ${f2(x.cohesion.mean)} · najsilniejsza ${f2(x.cohesion.max)}.` +
      (x.weakest ? ` Najsłabiej związana: sprawa ${x.weakest.case} (średnio ${f2(x.weakest.mean)} z pozostałymi).` : "")));
  }
  if (x.signature.length) {
    const byFeature = new Map();
    for (const s of x.signature) byFeature.set(s.feature, [...(byFeature.get(s.feature) || []), s]);
    items.push(el("div", { class: "sig" }, [el("h5", { text: "Wspólna sygnatura (wartości w co najmniej połowie spraw)" }),
      el("dl", { class: "fields sig-list" }, [...byFeature].flatMap(([feat, vals]) => [el("dt", { text: featureName(feat) }),
        el("dd", {}, chips(vals.slice(0, 10).map((v) => `${valueText(feat, v.value)} · ${v.count}/${v.of}`), TRACES.has(feat) ? "tag ev-tag" : "tag"))]))]));
  }
  if (x.nearest) items.push(el("p", { class: "sep", text: separation(x.nearest) }));
  return el("div", { class: "why-box" }, [el("h5", { text: "Dlaczego te sprawy są razem" }), ...items]);
}

function linkRow(l) {
  const detail = el("div", { class: "link-detail", hidden: "" });
  const btn = el("button", { type: "button", class: "link-btn why", "aria-expanded": "false", text: "Dlaczego?" });
  btn.addEventListener("click", async () => {
    const open = btn.getAttribute("aria-expanded") !== "true";
    btn.setAttribute("aria-expanded", String(open));
    detail.hidden = !open;
    if (!open || detail.childElementCount) return;
    detail.append(note("Liczę uzasadnienie…"));
    try {
      detail.replaceChildren(pairView(await fetchPair(l.a, l.b), `Sprawa ${l.a}`, `Sprawa ${l.b}`));
    } catch (e) {
      detail.replaceChildren(note(e.message, "message error"));
    }
  });
  return el("li", {}, [el("span", { class: "pair", text: `${l.a} ↔ ${l.b}` }), el("span", { class: "sc", text: f2(l.score) }),
    l.evidence.length ? el("span", { class: "ev", text: l.evidence.map(evRaw).join("; ") }) : el("span", { class: "none", text: "brak dowodów" }),
    btn, detail]);
}

function groupRow(g) {
  const ids = g.members.map((m) => m.case);
  const hit = state.joined.some((j) => j.length === ids.length && j.every((c) => ids.includes(c)));
  const summary = el("summary", {}, [
    el("span", { class: "g-no", text: `K${g.no}` }),
    el("span", { class: "g-fam", text: `rodzina ${g.family}` }),
    el("span", { class: "g-main" }, [el("span", { class: "g-type", text: SCAM[g.scam_type] || g.scam_type }),
      el("span", { class: "g-ids", text: ids.join(" · ") }), hit ? el("span", { class: "tag solid", text: "pasuje nowy artykuł" }) : null]),
    el("span", { class: "g-count", text: casesPl(ids.length) }),
  ]);
  const links = g.links.slice(0, 8).map(linkRow);
  const row = el("details", { class: "group" + (hit ? " hit" : "") }, [summary, el("div", { class: "group-body" }, [
    campaignWhy(g.explanation),
    links.length ? el("ul", { class: "links", "aria-label": "Powiązania między sprawami" }, links) : null,
    el("div", { class: "cases" }, g.members.map((m) => caseCard(m, `Sprawa ${m.case}`))),
  ])]);
  row.open = hit;
  return row;
}

export async function loadGroups() {
  try {
    const data = await api(`/api/groups?tau=${tau()}`);
    state.groupsTau = data.tau;
    state.groupNo = new Map(data.groups.map((g) => [keyOf(g.members.map((m) => m.case)), g.no]));
    $("groups-hint").textContent = `Kampania: sprawy połączone twardym dowodem, prawie identyczną treścią albo średnim podobieństwem ≥ τ = ${f2(data.tau)}. ` +
      "Rodzina: kampanie z tym samym typem oszustwa i wynikiem ≥ 0.30 albo wspólnym narzędziem, zestawem stron lub szablonem śledzenia.";
    $("groups-count").textContent = `[${data.groups.length}]`;
    $("groups").replaceChildren(el("div", { class: "groups" }, data.groups.map(groupRow)));
  } catch (e) {
    $("groups").replaceChildren(note(`Nie udało się wczytać grup: ${e.message}`, "message error"));
  }
}
