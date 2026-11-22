// Folder tabs: Analizator, Rozpoznane grupy, Graf powiązań (keyboard: left and right arrows).
import { $, smooth } from "./dom.js";

const TABS = { analizator: ["tab-analiza", "panel-analiza"], grupy: ["tab-grupy", "panel-grupy"], graf: ["tab-graf", "panel-graf"] };
const ORDER = Object.keys(TABS);
const onShowHandlers = {};

export const onShow = (name, fn) => { onShowHandlers[name] = fn; };
export const visible = (name) => !$(TABS[name][1]).hidden;

export function showTab(name, focus = false) {
  for (const [key, [tabId, panelId]] of Object.entries(TABS)) {
    const on = key === name;
    $(tabId).setAttribute("aria-selected", String(on));
    $(tabId).tabIndex = on ? 0 : -1;
    $(panelId).hidden = !on;
  }
  if (focus) $(TABS[name][0]).focus();
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (onShowHandlers[name]) onShowHandlers[name]();
}

export function openCase(cid) {
  showTab("grupy");
  const card = document.getElementById(`case-${cid}`);
  if (!card) return;
  card.closest("details").open = true;
  card.scrollIntoView({ behavior: smooth(), block: "center" });
  card.focus({ preventScroll: true });
}

export function initTabs() {
  for (const [key, [tabId]] of Object.entries(TABS)) {
    $(tabId).addEventListener("click", () => showTab(key));
    $(tabId).addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      ev.preventDefault();
      const step = ev.key === "ArrowRight" ? 1 : ORDER.length - 1;
      showTab(ORDER[(ORDER.indexOf(key) + step) % ORDER.length], true);
    });
  }
  showTab(ORDER.includes(location.hash.slice(1)) ? location.hash.slice(1) : "analizator");
}
