// Entry point: wires the tabs, the analyser, the threshold slider and the status line.
import { $, api, casesPl, el, tau } from "./dom.js";
import { state } from "./state.js";
import { initAnalyser } from "./analyser.js";
import { loadGraph } from "./graph.js";
import { loadGroups } from "./groups.js";
import { initTraitSelect } from "./bytrait.js";
import { initTabs, onShow, visible } from "./tabs.js";

async function loadStatus() {
  try {
    const s = await api("/api/status");
    $("status").replaceChildren(el("b", { text: casesPl(s.cases) }), " w bazie · ",
      s.llm ? "LLM gotowy" : el("span", { class: "warn", text: "brak klucza LLM" }));
    $("analyse-btn").disabled = !s.llm;
  } catch (e) {
    $("status").textContent = "serwer nie odpowiada";
  }
}

onShow("graf", loadGraph);
initAnalyser(() => Promise.all([loadStatus(), loadGroups()]));
$("tau").addEventListener("input", () => { $("tau-out").textContent = tau().toFixed(2); });
$("tau").addEventListener("change", () => {
  state.joined = [];
  loadGroups();
  if (visible("graf")) loadGraph();
});
initTabs();
initTraitSelect(loadGroups);
loadStatus();
loadGroups();
