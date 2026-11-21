"""Streamlit demonstrator.   Run from the repo root:   streamlit run src/ads/app.py

Tabs
  1. Analyse: pick a sample case, or give new material (screenshot / HTML file / URL / pasted text / product
     name). New material goes through the LLM extraction, then is compared with the database.
  2. Campaigns: groups at the chosen threshold and a graph of links between cases.
  3. Evaluation: ranking-constraint and clustering metrics against the gold labels (if present).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st  # noqa: E402

from ads import cluster as clu  # noqa: E402
from ads import evaluate as ev  # noqa: E402
from ads.similarity import score  # noqa: E402

MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-flash-lite"]
COLORS = {"fake_investment": "#4C78A8", "miracle_cure": "#54A24B", "fake_online_casino": "#E45756",
          "fake_online_shop": "#F58518", "other": "#999999"}

st.set_page_config(page_title="Follow the Fake", layout="wide")


@st.cache_data
def database():
    return ev.load_profiles()


def label(cid, p):
    e, v = p["entities"], p["visual_and_production"]
    name = e["product_or_platform"]["exact_name"] or p["core_narrative"]["topic"]
    return f"{cid}: {name} ({v['ad_creative_template'] or 'no ad template'} -> {v['landing_page_template'] or 'no page'})"


def pname(x):
    return x["name"] or "unnamed " + str(x["category_or_role"])


def show_profile(p):
    n, e, v = p["core_narrative"], p["entities"], p["visual_and_production"]
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Scam type:** `{n['ad_goal_scam_type']}`  \n**Topic:** `{n['topic']}`  \n**CTA:** {n['call_to_action']}")
    c2.markdown(f"**Ad template:** `{v['ad_creative_template']}`  \n**Page template:** `{v['landing_page_template']}`  \n"
                f"**Funnel:** {' -> '.join(v['funnel_stages'])}")
    people = ", ".join(pname(x) for x in e["featured_people"]) or "-"
    c3.markdown(f"**Product:** {e['product_or_platform']['exact_name']}  \n**Media:** {', '.join(e['impersonated_media']) or '-'}  \n"
                f"**People:** {people}")
    st.markdown(f"**Persuasion devices:** {', '.join(n['persuasion_devices']) or '-'}")
    st.info(p["canonical_comparison_text"])
    with st.expander("Technical traces"):
        st.json(p["technical_artifacts"])


def show_neighbours(profile, db, tau):
    res = clu.assign(profile, db, tau)
    if res["is_new_group"]:
        st.warning(f"No existing case reaches the threshold ({tau:.2f}): this looks like a NEW campaign (unconfirmed).")
    else:
        st.success("Joins group(s): " + " | ".join(", ".join(g) for g in res["joins"]))
    for cid, r in res["neighbours"]:
        with st.expander(f"{label(cid, db[cid])}  —  score {r['score']:.2f}", expanded=r["score"] >= tau):
            if r["strong_links"]:
                st.markdown("**Strong evidence:** " + "; ".join(r["strong_links"]))
            top = sorted(r["contributions"].items(), key=lambda x: -x[1])
            st.markdown("**Why similar (weighted contribution):** " + ", ".join(f"{k} {v:.2f}" for k, v in top if v > 0) or "-")
            st.caption("Not comparable (missing on one side): " + (", ".join(r["missing"]) or "-"))


def build_case(files, url, text, product):
    """Turn user input into an in-memory case_input (images + page text)."""
    parts, tmp = [], tempfile.mkdtemp()
    images = []
    for f in files or []:
        path = os.path.join(tmp, f.name)
        open(path, "wb").write(f.getbuffer())
        if f.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            images.append(path)
        elif f.name.lower().endswith((".html", ".htm")):
            from ads.preprocess.assemble import html_to_text
            parts.append({"role": "bridge_page", "medium": "html", "text": html_to_text(path), "images": []})
    if images:
        parts.insert(0, {"role": "ad_creative", "medium": "image", "text": None, "images": images})
    page_text = text or ""
    if url:
        try:
            import requests
            from ads.preprocess.assemble import html_to_text
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) Mobile", "Accept-Language": "pl-PL"})
            p = os.path.join(tmp, "page.html")
            open(p, "wb").write(r.content)
            page_text += "\n" + html_to_text(p)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Could not fetch the URL ({e}); using the other inputs.")
    if product:
        page_text = f"Product or platform named by the analyst: {product}\n" + page_text
    if page_text.strip():
        parts.append({"role": "bridge_page" if images else "offer_page", "medium": "text", "text": page_text.strip(), "images": []})
    if not parts:
        return None
    tech = {"urls_and_domains": [url] if url else [], "redirect_chain": [url] if url else [], "tracker_ids": [],
            "dom_and_form_clues": [], "domain_and_cert_metadata": []}
    return {"schema_version": "1.0", "case_id": "new", "parts": parts, "technical_summary": tech, "resolved_identities": []}


db = database()
st.title("Follow the Fake: linking scam ads into campaigns")
if not db:
    st.error("No extracted profiles found in data/cases/*/profile.json. Run the assemble and extract steps first (see README).")
    st.stop()

with st.sidebar:
    tau = st.slider("Similarity threshold (join a group)", 0.2, 0.95, 0.6, 0.01)
    model = st.selectbox("LLM for new material", MODELS, help="Free-tier quota is per model; switch if one is exhausted.")
    st.caption(f"{len(db)} cases in the database")

tab1, tab2, tab3 = st.tabs(["Analyse", "Campaigns", "Evaluation"])

with tab1:
    mode = st.radio("Input", ["Sample case from the database", "New material"], horizontal=True)
    if mode == "Sample case from the database":
        cid = st.selectbox("Case", sorted(db), format_func=lambda c: label(c, db[c]))
        show_profile(db[cid])
        st.subheader("Most similar cases")
        rest = {k: v for k, v in db.items() if k != cid}
        show_neighbours(db[cid], rest, tau)
    else:
        files = st.file_uploader("Ad screenshot(s) and/or saved HTML page", accept_multiple_files=True,
                                 type=["png", "jpg", "jpeg", "webp", "html", "htm"])
        c1, c2 = st.columns(2)
        url = c1.text_input("Landing page URL (optional)")
        product = c2.text_input("Product or platform name (optional)")
        text = st.text_area("Pasted ad or page text (optional)", height=120)
        if st.button("Analyse", type="primary"):
            case = build_case(files, url, text, product)
            if not case:
                st.error("Give at least a screenshot, a URL, some text or a product name.")
            else:
                with st.spinner("Extracting features with the LLM (cached after the first run)..."):
                    try:
                        from ads.llm.client import make_client
                        from ads.llm.extract import extract
                        prof = extract(case, make_client(extraction_model=model))
                        st.session_state["new_profile"] = prof
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Extraction failed: {str(e)[:400]}")
        if "new_profile" in st.session_state:
            prof = st.session_state["new_profile"]
            show_profile(prof)
            st.subheader("Comparison with the database")
            show_neighbours(prof, db, tau)

with tab2:
    scores = clu.pair_scores(db)
    groups = clu.cluster(db, tau, scores)
    st.subheader(f"Groups at threshold {tau:.2f}")
    for g in groups:
        st.markdown(f"- **{len(g)} case(s):** " + "; ".join(label(c, db[c]) for c in g))
    dot = ["graph G {", 'layout=neato; overlap=false; splines=true; node [style=filled, fontcolor=white, fontsize=11];']
    for cid, p in db.items():
        col = COLORS.get(p["core_narrative"]["ad_goal_scam_type"], "#999999")
        dot.append(f'"{cid}" [label="{cid}\\n{(p["entities"]["product_or_platform"]["exact_name"] or p["core_narrative"]["topic"])[:18]}", fillcolor="{col}"];')
    for (a, b), r in scores.items():
        if r["score"] >= tau * 0.8:
            strong = bool(r["strong_links"])
            dot.append(f'"{a}" -- "{b}" [penwidth={1 + 4 * r["score"]:.1f}, label="{r["score"]:.2f}", fontsize=9'
                       f'{", color=red" if strong else ""}];')
    dot.append("}")
    st.subheader("Link graph (edge = similarity; red = tracker / domain / endpoint evidence)")
    st.graphviz_chart("\n".join(dot))
    st.caption("Node colour = scam type: " + ", ".join(f"{k}" for k in COLORS))

with tab3:
    gold_path = next((p for p in (os.path.join(ev.REPO, "data", "gold", "groups.local.json"),
                                  os.path.join(ev.REPO, "data", "gold", "groups.json")) if os.path.exists(p)), None)
    if not gold_path:
        st.info("No gold labels found in data/gold/.")
    else:
        gold = json.load(open(gold_path, encoding="utf-8"))
        r = ev.evaluate(db, gold, tau)
        ok = sum(t[3] for t in r["triples"])
        m1, m2, m3 = st.columns(3)
        m1.metric("Ranking constraints satisfied", f"{ok}/{len(r['triples'])}")
        m2.metric("Strict F1 (same campaign/template)", f"{r['strict'][2]:.2f}")
        m3.metric("Broad precision", f"{r['broad'][0]:.2f}")
        for t, c, f, good in r["triples"]:
            st.write(("✅ " if good else "❌ ") + f"similarity({t['anchor']},{t['closer']}) = {c:.2f}  >  similarity({t['anchor']},{t['farther']}) = {f:.2f}  — {t['reason']}")
