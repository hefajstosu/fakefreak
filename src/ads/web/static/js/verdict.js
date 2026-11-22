// Why the verdict, and which campaigns and families a new article joined (ads/explain/joins.py).
import { el, f2 } from "./dom.js";
import { GROUP, evText } from "./labels.js";

const CONTENT_RULES = new Set(["capture", "content", "hard_evidence"]);

function ruleLine(r) {
  const x = r.reasons, t = x.thresholds, s = f2(x.top_score), c = x.top_case, dup = x.duplicates[0];
  const ev = (list) => list.map(evText).join("; ");
  switch (x.rule) {
    case "capture": return [`Ten sam materiał co sprawa ${dup.case}: ${dup.reasons.join("; ")}. Dołączony do tamtego wpisu, nie liczony jako nowy.`];
    case "content": return [`Ta sama treść co sprawa ${dup.case} (${dup.reasons.join("; ")}), ale inne ślady techniczne: typowe dla jednej kampanii przeniesionej na nowe domeny.`];
    case "empty": return ["Baza jest pusta, więc nie ma z czym porównać."];
    case "score_confirm": return [`Najbliższa sprawa ${c}: wynik ${s} ≥ ${f2(t.confirm)} (prawie ta sama treść).`];
    case "tau_and_evidence": return [`Najbliższa sprawa ${c}: wynik ${s} ≥ τ = ${f2(t.tau)} i dowód: ${ev(x.evidence)}.`];
    case "hard_evidence": return [
      `Twardy dowód ze sprawą ${x.hard_case}: ${ev(x.hard_evidence)}. Taki dowód łączy z kampanią niezależnie od podobieństwa treści (tu ${f2(x.hard_score)}; τ = ${f2(t.tau)}).`,
      ...(c !== x.hard_case ? [`Najbliższa sprawa pod względem treści to ${c} (${s}); tabela niżej pokazuje, do której kampanii należy.`] : [])];
    case "tau_only": return [`Najbliższa sprawa ${c}: wynik ${s} ≥ τ = ${f2(t.tau)}, ale bez twardego dowodu (tracker, strona sponsorująca, identyfikator kampanii, certyfikat). Potrzebne potwierdzenie analityka.`];
    case "family_evidence": return [`Dowód rodziny ze sprawą ${x.family_case}: ${ev(x.family_evidence)}. To samo narzędzie, zestaw stron lub szablon śledzenia i ten sam typ oszustwa: ta sama rodzina kampanii. Mogą ich używać różni operatorzy, a wynik treści (${f2(x.family_score)}) jest za niski na tę samą kampanię.`];
    case "family": return [`Najbliższa sprawa ${c}: wynik ${s} < τ = ${f2(t.tau)}, ale ≥ ${f2(t.family)} (próg rodziny). Materiał przypomina znaną rodzinę oszustw, za mało na tę samą kampanię (tak wygląda np. sama reklama bez strony docelowej).`];
    case "nothing": return [`Najbliższa sprawa ${c}: wynik ${s} < ${f2(t.family)} (próg rodziny). Nic w bazie nie jest blisko: kandydat na nową kampanię.`];
    default: return [`${r.decision.title}. ${r.decision.explanation}`];
  }
}

export function reasonLines(r) {
  const lines = ruleLine(r);
  const top = r.neighbours[0];
  if (top && !CONTENT_RULES.has(r.reasons.rule)) {
    const groups = top.explanation.groups;
    const main = [...groups].sort((p, q) => q.contribution - p.contribution)[0];
    if (main) lines.push(`Do wyniku ze sprawą ${top.case} najwięcej wnosi grupa „${GROUP[main.group][0]}” (+${f2(main.contribution)}); bez niej wynik wyniósłby ${f2(main.without)}.`);
    const crossing = groups.filter((g) => g.crosses_tau);
    lines.push(crossing.length
      ? `Decyzja zależy od grup: ${crossing.map((g) => `„${GROUP[g.group][0]}”`).join(", ")}. Bez którejkolwiek z nich wynik znalazłby się po drugiej stronie progu τ.`
      : "Żadna pojedyncza grupa cech nie przesuwa wyniku przez próg τ: decyzja jest stabilna.");
  }
  const t = r.reasons.thresholds;
  lines.push(`Progi: τ = ${f2(t.tau)} (kampania), ${f2(t.family)} (rodzina), ${f2(t.confirm)} (prawie ta sama treść).`);
  return lines;
}

export function hardSummary(row) {  // "sprawy 1, 2: <evidence>", one line per distinct piece of evidence
  const by = new Map();
  for (const h of row.hard) {
    for (const e of h.evidence.filter((x) => x.must_link)) by.set(evText(e), [...(by.get(evText(e)) || []), h.case]);
  }
  return [...by].map(([ev, cases]) => `${cases.length > 1 ? "sprawy" : "sprawa"} ${cases.join(", ")}: ${ev}`);
}

export function campaignResult(row, thresholds) {
  if (!row.joined) return `nie dołączono: brakuje ${f2(row.gap)} do τ (najbliższa sprawa ${row.best.case}: ${f2(row.best.score)})`;
  if (row.rule === "hard evidence") return "dołączono: twardy dowód";
  if (row.rule === "same content") return `dołączono: prawie ta sama treść co sprawa ${row.best.case} (${f2(row.best.score)} ≥ ${f2(thresholds.confirm)})`;
  return "dołączono: średnia ≥ τ";
}

export function campaignRows(r) {
  return r.campaigns.map((row) => {
    const hard = hardSummary(row);
    return el("tr", { class: row.joined ? "joined" : null }, [
      el("td", {}, [el("b", { class: "case-link", text: row.no ? `K${row.no}` : "–" }), el("span", { class: "hint", text: ` ${row.members.join(", ")}` })]),
      el("td", { class: "num" }, [el("span", { class: "meter", "aria-hidden": "true" }, [
        el("i", { style: `width:${Math.round(row.mean * 100)}%` }), el("b", { class: "tau-mark", style: `left:${r.thresholds.tau * 100}%` })]), f2(row.mean)]),
      el("td", { class: hard.length ? "ev" : null, text: hard.join("; ") || "–" }),
      el("td", { text: campaignResult(row, r.thresholds) }),
    ]);
  });
}

export function familyText(r) {
  const joined = r.families.filter((f) => f.joined);
  if (!joined.length) return `Rodzina kampanii: żadna. Brak sprawy tego samego typu oszustwa z wynikiem ≥ ${f2(r.thresholds.family)} i brak dowodu rodziny.`;
  return joined.map((f) => {
    const why = [];
    if (f.evidence_with.length) why.push(`dowód rodziny (narzędzie, zestaw stron lub szablon śledzenia) ze sprawą ${f.evidence_with.join(", ")}`);
    if (f.score_with.length) why.push(`wynik ≥ ${f2(r.thresholds.family)} i ten sam typ oszustwa ze sprawą ${f.score_with.join(", ")}`);
    return `Rodzina kampanii (sprawy ${f.members.join(", ")}): dołączono, bo ${why.join("; ")}.`;
  }).join(" ");
}
