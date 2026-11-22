// DOM and HTTP helpers. Values from the server always go into the DOM as text, never as HTML: they come from scam pages.

export const $ = (id) => document.getElementById(id);
export const tau = () => Number($("tau").value);
export const f2 = (x) => (x == null ? "–" : Number(x).toFixed(2));
export const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
export const clipText = (t, n = 80) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
export const listText = (items, n = 6) =>
  items.slice(0, n).map((x) => clipText(String(x))).join(", ") + (items.length > n ? ` (+${items.length - n})` : "");
export const sizeText = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} kB`);

export function casesPl(n) {
  if (n === 1) return "1 sprawa";
  return [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? `${n} sprawy` : `${n} spraw`;
}

function build(node, props, children) {
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") node.setAttribute("class", v);
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c != null) node.append(c);
  return node;
}

export const el = (tag, props = {}, children = []) => build(document.createElement(tag), props, children);
export const svg = (tag, props = {}, children = []) =>
  build(document.createElementNS("http://www.w3.org/2000/svg", tag), props, children);
export const chips = (items, cls = "tag") => el("span", { class: "tags inline" }, items.map((t) => el("span", { class: cls, text: t })));
export const note = (text, cls = "hint") => el("p", { class: cls, text });

async function answer(res) {
  const data = await res.json().catch(() => ({ error: `Błąd serwera (${res.status})` }));
  if (!res.ok) throw new Error(data.error || `Błąd serwera (${res.status})`);
  return data;
}

export async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  return answer(await fetch(path, opts));
}

export async function postForm(path, fields, files) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, String(v));
  for (const f of files) form.append("files", f, f.name);
  return answer(await fetch(path, { method: "POST", body: form }));
}
