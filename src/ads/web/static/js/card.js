// One case as a card: a database case or the analysed article.
import { el } from "./dom.js";
import { SCAM, infraSummary } from "./labels.js";

export function caseCard(s, title) {
  const rows = [
    ["Typ", `${SCAM[s.scam_type] || s.scam_type} · ${s.topic}`],
    ["Produkt", s.product || "–"],
    ["Osoby", s.people.join(", ") || "–"],
    ["Podszywa się", s.media.join(", ") || "–"],
    ["Szablon", s.templates.replace(" -> ", " → ")],
    ["Domeny", s.domains.join(", ") || "–"],
    ["Trackery", String(s.trackers.length)],
    ["Domena", s.infra && s.infra.length ? infraSummary(s.infra) : "–"],
  ];
  const body = el("div", { class: "case-body" }, [
    el("div", { class: "case-title" }, [el("h4", { text: title }),
      s.unconfirmed ? el("span", { class: "tag flag", text: "niepotwierdzona" }) : null]),
    el("dl", { class: "fields" }, rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })])),
    s.persuasion.length ? el("div", { class: "tags" }, s.persuasion.map((p) => el("span", { class: "tag", text: p.replaceAll("_", " ") }))) : null,
    el("p", { class: "summary", text: s.summary, title: s.summary }),
  ]);
  const img = s.image_url
    ? el("figure", {}, el("img", { src: s.image_url, alt: `Zrzut reklamy, sprawa ${s.case}`, loading: "lazy", width: "110", height: "150" }))
    : null;
  const id = s.case === "new" ? null : `case-${s.case}`;
  return el("article", { class: "case" + (img ? "" : " noimg"), id, tabindex: id ? "-1" : null }, [img, body]);
}
