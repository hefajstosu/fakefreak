// The analysis as a Markdown report, built from the same data as the page.
import { el, f2, listText } from "./dom.js";
import { GROUP, STATUS, evText, featureName, linkKind, pretty } from "./labels.js";
import { state } from "./state.js";
import { sharedText } from "./explain.js";
import { campaignResult, familyText, hardSummary, reasonLines } from "./verdict.js";

function neighbour(n) {
  const ex = n.explanation;
  const md = [`### Sprawa ${n.case}: wynik ${f2(ex.score)}${ex.must_link ? " (twardy dowód)" : ""}`, ""];
  for (const e of ex.evidence) md.push(`- Dowód: ${evText(e)} (${linkKind(e)})`);
  md.push("", "| Grupa cech | Wkład | Podobieństwo | Wynik bez tej grupy |", "|---|---|---|---|");
  for (const g of ex.groups) md.push(`| ${GROUP[g.group][0]} | +${f2(g.contribution)} | ${Math.round((g.similarity || 0) * 100)}% | ${f2(g.without)}${g.crosses_tau ? " (zmienia stronę progu)" : ""} |`);
  md.push("", "Wspólne:");
  for (const f of ex.features.filter((x) => (x.contribution || 0) > 0).slice(0, 8)) {
    md.push(`- ${featureName(f.feature)} (${Math.round(f.similarity * 100)}%, +${f2(f.contribution)}): ${sharedText(f)}`);
  }
  const lost = ex.features.filter((f) => (f.loss || 0) >= 0.015).sort((x, y) => y.loss - x.loss).slice(0, 5);
  if (lost.length) md.push("", "Różnice:");
  for (const f of lost) {
    const v = f.values || {};
    const diff = v.only_a ? `tylko artykuł: ${listText(v.only_a) || "–"}; tylko sprawa: ${listText(v.only_b) || "–"}`
      : v.shared_words ? "inne sformułowania" : `${pretty(v.a)} / ${pretty(v.b)}`;
    md.push(`- ${featureName(f.feature)} (−${f2(f.loss)}): ${diff}`);
  }
  const missing = ex.features.filter((f) => f.contribution == null && f.missing && f.missing !== "both");
  if (missing.length) md.push("", `Pominięte z braku danych: ${missing.map((f) => featureName(f.feature)).join(", ")}`);
  return [...md, ""];
}

export function reportMarkdown(r, source) {
  const [, stamp, heading] = STATUS[r.decision.status] || ["", r.decision.status, r.decision.status];
  const p = r.profile;
  return [
    "# Raport analizy artykułu", "", `Data: ${new Date().toLocaleString("pl-PL")}  `, `Źródło: ${source || "wklejony tekst"}  `,
    `Próg τ: ${f2(r.thresholds.tau)}`, "", "## Werdykt", "", `**${stamp}**: ${heading}`, "", ...reasonLines(r).map((l) => `- ${l}`), "",
    "## Dopasowanie do kampanii", "", "| Kampania | Sprawy | Średnie podobieństwo | Twardy dowód | Wynik |", "|---|---|---|---|---|",
    ...r.campaigns.map((row) => `| ${row.no ? `K${row.no}` : "–"} | ${row.members.join(", ")} | ${f2(row.mean)} | ${hardSummary(row).join("; ") || "–"} | ${campaignResult(row, r.thresholds)} |`),
    "", familyText(r), "", "## Najbliższe sprawy i uzasadnienie", "", ...r.neighbours.flatMap(neighbour),
    "## Profil artykułu (LLM)", "", `- Typ: ${pretty(p.scam_type)} · ${p.topic}`, `- Produkt: ${p.product || "–"}`,
    `- Osoby: ${p.people.join(", ") || "–"}`, `- Podszywa się: ${p.media.join(", ") || "–"}`, `- Szablon: ${p.templates}`,
    `- Domeny: ${p.domains.join(", ") || "–"}`, `- Techniki perswazji: ${p.persuasion.map(pretty).join(", ") || "–"}`, "", p.summary || "", "",
    "---", "Wynik = średnia ważona podobieństw cech dostępnych po obu stronach; wkłady grup sumują się do wyniku. " +
    "Twardy dowód (wspólny tracker, strona sponsorująca, identyfikator kampanii reklamowej, certyfikat) łączy w kampanię niezależnie od wyniku; " +
    "wspólne narzędzie, zestaw stron lub szablon śledzenia łączą w rodzinę. Demografia osób niezidentyfikowanych nie wpływa na wynik. " +
    "Raport zawiera dane z materiałów: nie publikować.",
  ].join("\n");
}

export function downloadReport() {
  const r = state.lastResult;
  if (!r) return;
  const blob = new Blob([reportMarkdown(r, state.lastInput)], { type: "text/markdown;charset=utf-8" });
  const a = el("a", { href: URL.createObjectURL(blob), download: `raport-${r.decision.status}-${Date.now()}.md` });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}
