// The analyser tab: the form with its files, the verdict, campaigns, neighbours and saving.
import { $, api, el, f2, postForm, sizeText, smooth, tau } from "./dom.js";
import { STATUS, evRaw } from "./labels.js";
import { state } from "./state.js";
import { caseCard } from "./card.js";
import { pairView } from "./explain.js";
import { loadGroups } from "./groups.js";
import { downloadReport } from "./report.js";
import { openCase, showTab } from "./tabs.js";
import { campaignRows, familyText, reasonLines } from "./verdict.js";

const KIND = {  // extension -> label (ads/analysis/case.py FILE_KINDS)
  png: "zrzut", jpg: "zrzut", jpeg: "zrzut", webp: "zrzut", gif: "zrzut", html: "strona HTML", htm: "strona HTML",
  har: "log sieci HAR", txt: "tekst", mp4: "wideo", mov: "wideo", webm: "wideo", m4v: "wideo",
};
const MAX_UPLOAD_MB = 200;
let chosen = [];

const kindOf = (f) => KIND[(f.name.split(".").pop() || "").toLowerCase()];

function renderFiles() {
  $("file-list").replaceChildren(...chosen.map((f, i) => {
    const rm = el("button", { type: "button", "aria-label": `Usuń ${f.name}`, text: "usuń" });
    rm.addEventListener("click", () => { chosen.splice(i, 1); renderFiles(); });
    return el("li", {}, [el("span", { class: "fname", text: f.name }),
      el("span", { class: "fkind" + (kindOf(f) ? "" : " bad"), text: kindOf(f) || "nieobsługiwany" }),
      el("span", { class: "fsize", text: sizeText(f.size) }), rm]);
  }));
}

function addFiles(list) {
  for (const f of list) if (!chosen.some((c) => c.name === f.name && c.size === f.size)) chosen.push(f);
  renderFiles();
}

function showNeighbourWhy(n) {
  $("pair-block").hidden = false;
  $("pair-code").textContent = `nowy ↔ ${n.case}`;
  $("pair-detail").replaceChildren(pairView(n.explanation, "Analizowany artykuł", `Sprawa ${n.case}`));
  $("pair-block").scrollIntoView({ behavior: smooth(), block: "start" });
}

function neighbourRow(n) {
  const link = el("a", { href: "#grupy", text: n.case });
  link.addEventListener("click", (ev) => { ev.preventDefault(); openCase(n.case); });
  const why = el("button", { type: "button", class: "link-btn why", text: "Dlaczego?" });
  why.addEventListener("click", () => showNeighbourWhy(n));
  return el("tr", {}, [
    el("td", {}, link),
    el("td", { class: "num" }, [el("span", { class: "meter", "aria-hidden": "true" }, el("i", { style: `width:${Math.round(n.score * 100)}%` })), f2(n.score)]),
    el("td", { text: n.product || "–" }),
    el("td", { class: n.evidence.length ? "ev" : null, text: n.evidence.map(evRaw).join("; ") || "–" }),
    el("td", {}, why),
  ]);
}

function showResult(r) {
  const [cls, stamp, heading] = STATUS[r.decision.status] || ["info", r.decision.status, r.decision.status];
  const lines = reasonLines(r);
  const notes = [...r.notes, ...(r.llm_used ? [] : ["duplikat rozpoznany bez wywołania LLM (użyto profilu z bazy)"])];
  $("verdict-code").textContent = r.decision.status;
  $("decision").replaceChildren(...[el("span", { class: `stamp ${cls}`, text: stamp }), el("strong", { text: heading }),
    el("p", { text: lines[0] }), notes.length ? el("p", { class: "notes", text: `Uwagi z wczytania: ${notes.join("; ")}` }) : null].filter(Boolean));
  $("reasons").replaceChildren(el("h5", { text: "Dlaczego taki werdykt: szczegóły" }),
    el("ul", { class: "reason-list" }, lines.slice(1).map((l) => el("li", { text: l }))));
  $("campaigns").tBodies[0].replaceChildren(...campaignRows(r));
  $("family-line").textContent = familyText(r);
  $("pair-block").hidden = true;
  $("profile").replaceChildren(caseCard(r.profile, "Analizowany artykuł"));
  $("neighbours").tBodies[0].replaceChildren(...r.neighbours.map(neighbourRow));
  $("save-btn").disabled = false;
  $("save-msg").textContent = "";
  $("result").hidden = false;
}

function message(text, cls = "message") {
  $("form-msg").className = cls;
  $("form-msg").textContent = text;
}

async function analyse(ev) {
  ev.preventDefault();
  const url = $("url").value.trim(), text = $("text").value.trim();
  const files = chosen.filter(kindOf);
  const total = files.reduce((n, f) => n + f.size, 0);
  if (!url && !text && !files.length) return message("Podaj adres URL, wklej tekst artykułu albo dodaj jego pliki.", "message error");
  if (total > MAX_UPLOAD_MB * 1e6) return message(`Pliki mają razem ${sizeText(total)}; limit to ${MAX_UPLOAD_MB} MB.`, "message error");
  $("analyse-btn").disabled = true;
  message(files.length ? `Wysyłam ${files.length} plik(ów) (${sizeText(total)}), czytam je i porównuję z bazą…`
    : "Pobieram stronę i porównuję z bazą…", "message busy");
  try {
    const fields = { url, text, tau: tau() };
    const r = files.length ? await postForm("/api/analyze", fields, files) : await api("/api/analyze", fields);
    Object.assign(state, { analysisId: r.id, joined: r.joins, lastResult: r,
      lastInput: [url, ...files.map((f) => f.name)].filter(Boolean).join(", ") });
    showResult(r);
    message("");
    loadGroups();
    $("result").scrollIntoView({ behavior: smooth() });
  } catch (e) {
    message(e.message, "message error");
  } finally {
    $("analyse-btn").disabled = false;
  }
}

export function initAnalyser(afterSave) {
  const drop = $("drop");
  drop.addEventListener("click", () => $("files").click());
  drop.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); $("files").click(); } });
  for (const name of ["dragenter", "dragover"]) drop.addEventListener(name, (ev) => { ev.preventDefault(); drop.classList.add("over"); });
  for (const name of ["dragleave", "drop"]) drop.addEventListener(name, (ev) => { ev.preventDefault(); drop.classList.remove("over"); });
  drop.addEventListener("drop", (ev) => addFiles(ev.dataTransfer.files));
  $("files").addEventListener("change", () => { addFiles($("files").files); $("files").value = ""; });
  $("analyse-form").addEventListener("submit", analyse);
  $("report-btn").addEventListener("click", downloadReport);
  $("show-groups-btn").addEventListener("click", () => {
    showTab("grupy");
    (document.querySelector(".group.hit") || $("panel-grupy")).scrollIntoView({ behavior: smooth() });
  });
  $("save-btn").addEventListener("click", async () => {
    $("save-btn").disabled = true;
    try {
      const r = await api("/api/save", { id: state.analysisId });
      $("save-msg").textContent = `Zapisano jako ${r.case_id} (lokalnie, data/cases; poza gitem).`;
      Object.assign(state, { joined: [], graphTau: null });
      await afterSave();
    } catch (e) {
      $("save-msg").textContent = e.message;
      $("save-btn").disabled = false;
    }
  });
}
