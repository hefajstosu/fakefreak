// The groups tab in "group by trait" mode: cases that share the same value of one trait (served by /api/group_by).
import { $, api, casesPl, el, note } from "./dom.js";
import { SCAM } from "./labels.js";
import { caseCard } from "./card.js";

const NONE = "brak wartości";

// Fills the selector once; the first option (campaigns by similarity) is already in the HTML.
export async function initTraitSelect(onChange) {
  const select = $("group-mode");
  try {
    const data = await api("/api/group_by?trait=");
    for (const t of data.traits) select.append(el("option", { value: t.key, text: t.label }));
  } catch (e) {
    return;  // the selector stays with campaigns only
  }
  select.addEventListener("change", onChange);
}

export const currentTrait = () => $("group-mode").value;

const valueText = (trait, v) => (v == null ? NONE : trait === "scam_type" ? SCAM[v] || v : v.replaceAll("_", " "));

function traitRow(trait, label, g, no) {
  const ids = g.members.map((m) => m.case);
  return el("details", { class: "group" }, [
    el("summary", {}, [
      el("span", { class: "g-no", text: `G${no}` }),
      el("span", { class: "g-fam", text: label }),
      el("span", { class: "g-main" }, [el("span", { class: "g-type", text: valueText(trait, g.value) }),
        el("span", { class: "g-ids", text: ids.join(" · ") })]),
      el("span", { class: "g-count", text: casesPl(ids.length) }),
    ]),
    el("div", { class: "group-body" }, [el("div", { class: "cases" }, g.members.map((m) => caseCard(m, `Sprawa ${m.case}`)))]),
  ]);
}

export async function loadByTrait(trait) {
  try {
    const data = await api(`/api/group_by?trait=${encodeURIComponent(trait)}`);
    const label = (data.traits.find((t) => t.key === trait) || { label: trait }).label;
    $("groups-hint").textContent = `Sprawy z tą samą wartością cechy „${label}”. Bez podobieństwa i progu τ; ` +
      "sprawa z kilkoma wartościami trafia do każdej z grup.";
    $("groups-count").textContent = `[${data.groups.length}]`;
    $("groups").replaceChildren(el("div", { class: "groups" }, data.groups.map((g, i) => traitRow(trait, label, g, i + 1))));
  } catch (e) {
    $("groups").replaceChildren(note(`Nie udało się wczytać grup: ${e.message}`, "message error"));
  }
}
