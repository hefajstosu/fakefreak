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
from ads import decision as dec  # noqa: E402
from ads import dedup  # noqa: E402
from ads import evaluate as ev  # noqa: E402
from ads.similarity import score  # noqa: E402

MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash"]
COLORS = {"fake_investment": "#4C78A8", "miracle_cure": "#54A24B", "fake_online_casino": "#E45756",
          "fake_online_shop": "#F58518", "other": "#999999"}

st.set_page_config(page_title="Follow the Fake", layout="wide")


@st.cache_data
def database():
    return ev.load_profiles()


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


def show_neighbours(profile, db, tau, dups=None):
    """Compare with the database, show the graded decision, return it."""
    res = clu.assign(profile, db, tau)
    decision = dec.decide(res["neighbours"], dups or [], likely=tau)
    STATUS_BOX[decision["status"]](f"**{decision['title']}**  \n{decision['explanation']}")
    if dups:
        st.caption("Duplicate check: " + "; ".join(f"case {d['case']}: {', '.join(d['reasons'])}" for d in dups))
    for cid, r in res["neighbours"]:
        with st.expander(f"{label(cid, db[cid])}  —  score {r['score']:.2f}", expanded=r["score"] >= tau):
            if r["strong_links"]:
                st.markdown("**Strong evidence:** " + "; ".join(r["strong_links"]))
            top = sorted(r["contributions"].items(), key=lambda x: -x[1])
            st.markdown("**Why similar (weighted contribution):** " + ", ".join(f"{k} {v:.2f}" for k, v in top if v > 0) or "-")
            st.caption("Not comparable (missing on one side): " + (", ".join(r["missing"]) or "-"))
    return decision


def save_case(case, profile, decision=None):
    """Persist a scanned case as data/cases/web_<n>/ so it joins the database (gitignored directory)."""
    import shutil
    base = os.path.join(ev.REPO, "data", "cases")
    n = 1
    while os.path.exists(os.path.join(base, f"web_{n}")):
        n += 1
    cid = f"web_{n}"
    d = os.path.join(base, cid)
    os.makedirs(d)
    case = json.loads(json.dumps(case))
    case["case_id"] = cid
    for part in case["parts"]:
        saved = []
        for img in part.get("images", []):
            shutil.copy(img, os.path.join(d, os.path.basename(img)))
            saved.append(f"cases/{cid}/{os.path.basename(img)}")
        part["images"] = saved
    json.dump(case, open(os.path.join(d, "case_input.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(profile, open(os.path.join(d, "profile.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    status = (decision or {}).get("status")
    meta = {"decision": status}
    if status == "duplicate":
        meta["duplicate_of"] = decision["join"][0]
    elif status in ("new_unconfirmed", "suggested_family", "likely"):
        meta["status"] = "unconfirmed"      # an analyst confirms it later (Campaigns tab)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"))
    database.clear()
    fingerprints.clear()
    return cid


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
    scan = None
    if url:
        from ads.preprocess.url_scan import scan_url
        scan = scan_url(url)
        if scan["ok"]:
            page_text += chr(10) + scan["text"]
            for n in scan["notes"]:
                st.info(f"URL scan: {n}")
        else:
            st.warning(f"Could not scan the URL ({scan['error']}); using the other inputs.")
            scan = None
    if product:
        page_text = f"Product or platform named by the analyst: {product}\n" + page_text
    if page_text.strip():
        parts.append({"role": "bridge_page" if images else "offer_page", "medium": "text", "text": page_text.strip(), "images": []})
    if not parts:
        return None
    tech = scan["technical_summary"] if scan else {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [],
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
        fps = fingerprints()
        dups = dedup.find_duplicates(fps[cid], {k: v for k, v in fps.items() if k != cid}) if cid in fps else []
        show_neighbours(db[cid], rest, tau, dups)
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
                        st.session_state["new_case"] = case
                        st.session_state.pop("saved_id", None)
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Extraction failed: {str(e)[:400]}")
        if "new_profile" in st.session_state:
            prof = st.session_state["new_profile"]
            show_profile(prof)
            st.subheader("Comparison with the database")
            new_fp = dedup.fingerprint(st.session_state["new_case"])
            decision = show_neighbours(prof, db, tau, dedup.find_duplicates(new_fp, fingerprints()))
            if st.session_state.get("saved_id"):
                st.success(f"Saved to the database as {st.session_state['saved_id']} (data/cases/, not shared via git).")
            else:
                dup = decision["status"] == "duplicate"
                lbl = f"Save as duplicate of case {decision['join'][0]}" if dup else "Save to database"
                if st.button(lbl, help="Adds this scan to the database so later cases are compared with it. "
                                       "New or uncertain campaigns are saved as unconfirmed."):
                    st.session_state["saved_id"] = save_case(st.session_state["new_case"], prof, decision)
                    st.rerun()

with tab2:
    scores = clu.pair_scores(db)
    groups = clu.cluster(db, tau, scores)
    st.subheader(f"Groups at threshold {tau:.2f}")
    for g in groups:
        st.markdown(f"- **{len(g)} case(s):** " + "; ".join(label(c, db[c]) for c in g))
    unconfirmed = [c for c in db if ev.case_meta(c).get("status") == "unconfirmed"]
    if unconfirmed:
        st.subheader("Unconfirmed campaigns awaiting an analyst")
        pick = st.selectbox("Case", unconfirmed, format_func=lambda c: label(c, db[c]), key="confirm_pick")
        if st.button("Confirm this campaign"):
            f = os.path.join(ev.REPO, "data", "cases", pick, "meta.json")
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
