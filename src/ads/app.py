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

from ads import analyze as an  # noqa: E402
from ads import clustering as clu  # noqa: E402
from ads import dedup  # noqa: E402
from ads import evaluate as ev  # noqa: E402
from ads.paths import CASES, gold_file  # noqa: E402

MODELS = ["auto (tries several models)", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3-flash-preview",
          "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash"]

from ads.llm.client import QuotaExhausted, load_env  # noqa: E402

load_env()
KEY_OK = bool(os.environ.get("GEMINI_API_KEY"))
COLORS = {"fake_investment": "#4C78A8", "miracle_cure": "#54A24B", "fake_online_casino": "#E45756",
          "fake_online_shop": "#F58518", "other": "#999999"}

st.set_page_config(page_title="Follow the Fake", layout="wide")


@st.cache_data
def database():
    return ev.load_profiles()


@st.cache_data
def variant_db():
    """Synthetic variants of the database cases (extra comparisons only, never listed or grouped)."""
    return clu.load_variants(ev.load_profiles())


def label(cid, p):
    e, v = p["entities"], p["visual_and_production"]
    name = e["product_or_platform"]["exact_name"] or p["core_narrative"]["topic"]
    flag = " [unconfirmed]" if ev.case_meta(cid).get("status") == "unconfirmed" else ""
    return f"{cid}: {name} ({v['ad_creative_template'] or 'no ad template'} -> {v['landing_page_template'] or 'no page'}){flag}"


@st.cache_data
def fingerprints():
    return dedup.load_fingerprints()


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


STATUS_BOX = {"duplicate": st.success, "same_content": st.success, "confirmed": st.success, "likely": st.info,
              "suggested_family": st.warning, "new_unconfirmed": st.warning}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def render_comparison(res, db, tau):
    """Show the graded decision and the closest cases (res comes from analyze.compare or analyze.analyse)."""
    d = res["decision"]
    STATUS_BOX[d["status"]](f"**{d['title']}**  \n{d['explanation']}")
    if res["duplicates"]:
        st.caption("Duplicate check: " + "; ".join(f"case {x['case']}: {', '.join(x['reasons'])}" for x in res["duplicates"]))
    for cid, r in res["neighbours"]:
        with st.expander(f"{label(cid, db[cid])}  —  score {r['score']:.2f}", expanded=r["score"] >= tau):
            if r["strong_links"]:
                st.markdown("**Strong evidence:** " + "; ".join(r["strong_links"]))
            top = sorted(r["contributions"].items(), key=lambda x: -x[1])
            st.markdown("**Why similar (weighted contribution):** " + ", ".join(f"{k} {v:.2f}" for k, v in top if v > 0) or "-")
            st.caption("Not comparable (missing on one side): " + (", ".join(r["missing"]) or "-"))


def save_uploads(files):
    """Write uploaded files to a temporary folder; returns (screenshot paths, HTML page paths)."""
    tmp, images, pages = tempfile.mkdtemp(), [], []
    for f in files or []:
        path = os.path.join(tmp, f.name)
        open(path, "wb").write(f.getbuffer())
        if f.name.lower().endswith(IMAGE_EXT):
            images.append(path)
        elif f.name.lower().endswith((".html", ".htm")):
            pages.append(path)
    return images, pages


db = database()
st.title("Follow the Fake: linking scam ads into campaigns")
if not db:
    st.error("No extracted profiles found in data/cases/*/profile.json. Run the assemble and extract steps first (see README).")
    st.stop()

with st.sidebar:
    tau = st.slider("Similarity threshold (join a group)", 0.2, 0.95, 0.6, 0.01)
    model = st.selectbox("LLM for new material", MODELS,
                         help="'auto' tries the configured models in order and skips the ones out of free quota.")
    st.caption(f"{len(db)} cases in the database")
    _vars = variant_db()
    use_variants = st.checkbox("Use synthetic variants as extra comparisons", value=bool(_vars), disabled=not _vars,
                               help="Variants of database cases can raise a score; they are never shown as cases or grouped.")
    if _vars:
        st.caption(f"{sum(len(v) for v in _vars.values())} variants for {len(_vars)} cases (local, not in git)")
    VARIANTS = _vars if use_variants else None
    if KEY_OK:
        st.caption("LLM key: found. New material can be analysed.")
    else:
        st.warning("LLM key missing (GEMINI_API_KEY in .env). Sample cases, campaigns and evaluation still work; "
                   "analysing new material is disabled.")

tab1, tab2, tab3 = st.tabs(["Analyse", "Campaigns", "Evaluation"])

with tab1:
    mode = st.radio("Input", ["Sample case from the database", "New material"], horizontal=True)
    if mode == "Sample case from the database":
        cid = st.selectbox("Case", sorted(db), format_func=lambda c: label(c, db[c]))
        show_profile(db[cid])
        st.subheader("Most similar cases")
        rest = {k: v for k, v in db.items() if k != cid}
        fps = fingerprints()
        render_comparison(an.compare(db[cid], fps.get(cid), rest, tau, VARIANTS, fps), db, tau)
    else:
        files = st.file_uploader("Ad screenshot(s) and/or saved HTML page", accept_multiple_files=True,
                                 type=["png", "jpg", "jpeg", "webp", "html", "htm"])
        c1, c2 = st.columns(2)
        url = c1.text_input("Landing page URL (optional)")
        product = c2.text_input("Product or platform name (optional)")
        text = st.text_area("Pasted ad or page text (optional)", height=120)
        if not KEY_OK:
            st.error("No LLM key configured, so new material cannot be analysed here. Use a sample case, or add "
                     "GEMINI_API_KEY to .env and restart.")
        c_analyse, c_save, _ = st.columns([1, 3, 4])
        analyse = c_analyse.button("Analyse", type="primary", disabled=not KEY_OK)
        pending = None
        if "new_profile" in st.session_state:
            # a result is on screen: the Save button sits right next to Analyse
            prof = st.session_state["new_profile"]
            res = an.compare(prof, dedup.fingerprint(st.session_state["new_case"]), db, tau, VARIANTS, fingerprints())
            decision = res["decision"]
            pending = (prof, res)
            if st.session_state.get("saved_id"):
                c_save.success(f"Saved as {st.session_state['saved_id']} (local data/cases/, not shared via git)")
            else:
                dup = decision["status"] == "duplicate"
                lbl = f"Save as duplicate of case {decision['join'][0]}" if dup else "Save to database"
                if c_save.button(lbl, help="Adds this scan to the database so later cases are compared with it. "
                                           "New or uncertain campaigns are saved as unconfirmed."):
                    st.session_state["saved_id"] = an.save_case(st.session_state["new_case"], prof, decision)
                    database.clear()
                    fingerprints.clear()
                    st.rerun()
        if analyse:
            images, pages = save_uploads(files)
            case, notes = an.build_case(url, text, images, pages, product, text_role="bridge_page" if images else "offer_page")
            for note in notes:
                st.info(f"URL scan: {note}")
            done = False
            if not case:
                st.error("Give at least a screenshot, a URL, some text or a product name.")
            else:
                with st.spinner("Extracting features with the LLM (cached after the first run)..."):
                    try:
                        from ads.llm.client import make_client
                        client = make_client() if model.startswith("auto") else make_client(extraction_model=model)
                        st.session_state["new_profile"] = an.analyse(case, db, tau, client, VARIANTS, fingerprints())["profile"]
                        st.session_state["new_case"] = case
                        st.session_state.pop("saved_id", None)
                        done = True
                    except QuotaExhausted as e:
                        st.error("Every configured model is out of free quota right now (it resets about 09:00 Warsaw time). "
                                 "Sample cases still work; analyses you already ran are cached and free. "
                                 f"Details: {str(e)[:200]}")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Extraction failed: {str(e)[:400]}")
            if done:
                st.rerun()  # redraw so the Save button appears next to Analyse for the new result
        if pending and not analyse:
            prof, res = pending
            show_profile(prof)
            st.subheader("Comparison with the database")
            render_comparison(res, db, tau)

with tab2:
    scores = clu.pair_scores(db, VARIANTS)
    groups = clu.cluster(db, tau, scores)
    st.subheader(f"Groups at threshold {tau:.2f}")
    for g in groups:
        st.markdown(f"- **{len(g)} case(s):** " + "; ".join(label(c, db[c]) for c in g))
    unconfirmed = [c for c in db if ev.case_meta(c).get("status") == "unconfirmed"]
    if unconfirmed:
        st.subheader("Unconfirmed campaigns awaiting an analyst")
        pick = st.selectbox("Case", unconfirmed, format_func=lambda c: label(c, db[c]), key="confirm_pick")
        if st.button("Confirm this campaign"):
            f = os.path.join(CASES, pick, "meta.json")
            m = ev.case_meta(pick)
            m["status"] = "confirmed"
            json.dump(m, open(f, "w", encoding="utf-8"))
            st.rerun()
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
    gold_path = gold_file() if os.path.exists(gold_file()) else None
    if not gold_path:
        st.info("No gold labels found in data/gold/.")
    else:
        gold = json.load(open(gold_path, encoding="utf-8"))
        r = ev.evaluate(db, gold, tau, variants=VARIANTS)
        ok = sum(t[3] for t in r["triples"])
        m1, m2, m3 = st.columns(3)
        m1.metric("Ranking constraints satisfied", f"{ok}/{len(r['triples'])}")
        m2.metric("Strict F1 (same campaign/template)", f"{r['strict'][2]:.2f}")
        m3.metric("Broad precision", f"{r['broad'][0]:.2f}")
        for t, c, f, good in r["triples"]:
            st.write(("✅ " if good else "❌ ") + f"similarity({t['anchor']},{t['closer']}) = {c:.2f}  >  similarity({t['anchor']},{t['farther']}) = {f:.2f}  — {t['reason']}")
