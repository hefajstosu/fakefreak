"""Analyst panel: paste an article URL, see which known fake campaign it belongs to and what each campaign contains.

    streamlit run src/ads/panel.py          (from the repo root)

The full demo with screenshots, evaluation and the link graph is src/ads/app.py; the logic used here is ads/analyze.py.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st  # noqa: E402

from ads import analyze as an  # noqa: E402
from ads.evaluate import case_meta, load_profiles  # noqa: E402
from ads.llm.client import QuotaExhausted, load_env, make_client  # noqa: E402

STATUS = {  # decision status -> (box, heading)
    "duplicate": (st.success, "Duplikat sprawy, która już jest w bazie"),
    "same_content": (st.success, "Ta sama treść co znana kampania, inny host"),
    "confirmed": (st.success, "Pasuje do znanej kampanii (potwierdzone dowodem)"),
    "likely": (st.info, "Prawdopodobnie znana kampania"),
    "suggested_family": (st.warning, "Przypomina znaną rodzinę oszustw, za słabo na kampanię"),
    "new_unconfirmed": (st.warning, "Nowa kampania (do potwierdzenia przez analityka)"),
}

st.set_page_config(page_title="Panel fake'ów", layout="wide")
load_env()
KEY_OK = bool(os.environ.get("GEMINI_API_KEY"))


@st.cache_data
def database():
    return load_profiles()


@st.cache_data
def overview(tau: float, n_cases: int):  # n_cases invalidates the cache after a save
    return an.groups_overview(database(), tau)


def cases_pl(n: int) -> str:
    return f"{n} sprawa" if n == 1 else f"{n} sprawy" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else f"{n} spraw"


def show_case(s: dict, compact: bool = False) -> None:
    left, right = st.columns([1, 4])
    if s["image"]:
        left.image(s["image"], width=150)
    flag = " · niepotwierdzona" if case_meta(s["case"]).get("status") == "unconfirmed" else ""
    right.markdown(f"**Sprawa {s['case']}**{flag} · `{s['scam_type']}` · `{s['topic']}` · produkt: **{s['product'] or '-'}**")
    right.markdown(f"Osoby: {', '.join(s['people']) or '-'}  \nPodszywa się pod: {', '.join(s['media']) or '-'}  \n"
                   f"Szablon: `{s['templates']}`  \nDomeny: {', '.join(s['domains']) or '-'} · trackery: {len(s['trackers'])}")
    if not compact:
        right.caption(f"Triki: {', '.join(s['persuasion']) or '-'}")
        right.caption(s["summary"])


db = database()
with st.sidebar:
    tau = st.slider("Próg dołączenia do kampanii (τ)", 0.3, 0.9, 0.6, 0.05)
    st.caption(f"{cases_pl(len(db))} w bazie (data/cases)")
    if not KEY_OK:
        st.warning("Brak GEMINI_API_KEY w .env: przegląd grup działa, analiza nowych artykułów nie.")

st.title("Panel analizy artykułów")

# ---------------------------------------------------------------- analyse a new article
url = st.text_input("Adres URL artykułu", placeholder="https://...")
with st.expander("Strona się nie wczytuje albo pokazuje coś innego? Wklej jej tekst"):
    pasted = st.text_area("Tekst artykułu", height=150, label_visibility="collapsed")
if st.button("Analizuj", type="primary", disabled=not KEY_OK or not (url.strip() or pasted.strip())):
    with st.spinner("Pobieram stronę i porównuję z bazą..."):
        case, notes = an.case_from_url(url, pasted)
        st.session_state.pop("saved", None)
        if case is None:
            st.session_state["result"] = None
            st.error("Nie udało się zdobyć tekstu artykułu. " + "; ".join(notes) + " Wklej tekst ręcznie.")
        else:
            try:
                st.session_state["result"] = an.analyse(case, db, tau, make_client())
                st.session_state["case"], st.session_state["notes"] = case, notes
            except QuotaExhausted:
                st.error("Wszystkie modele wyczerpały limit zapytań. Przegląd grup nadal działa.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Analiza nie powiodła się: {str(e)[:300]}")

res = st.session_state.get("result")
if res:
    d = res["decision"]
    box, heading = STATUS[d["status"]]
    box(f"**{heading}**  \n{d['title']}. {d['explanation']}")
    if st.session_state.get("notes"):
        st.caption("Skan strony: " + "; ".join(st.session_state["notes"]))
    if not res["llm_used"]:
        st.caption("Duplikat rozpoznany bez wywołania LLM (użyto profilu z bazy).")
    st.subheader("Profil artykułu")
    show_case(an.case_summary("nowy", res["profile"]))
    st.subheader("Najbliższe sprawy")
    st.dataframe([{"sprawa": c, "podobieństwo": round(r["score"], 2), "twarde dowody": "; ".join(r["strong_links"]) or "-",
                   "produkt": an.case_summary(c, db[c])["product"]} for c, r in res["neighbours"]],
                 hide_index=True, width="stretch")
    if st.session_state.get("saved"):
        st.success(f"Zapisano jako {st.session_state['saved']} (lokalnie, data/cases; poza gitem).")
    elif st.button("Zapisz do bazy", help="Kolejne artykuły będą porównywane także z tym."):
        st.session_state["saved"] = an.save_case(st.session_state["case"], res["profile"], d)
        database.clear()
        st.rerun()

# ---------------------------------------------------------------- the known groups
st.header("Grupy fake'ów w bazie")
st.caption(f"Kampania = sprawy połączone twardym dowodem albo średnim podobieństwem ≥ τ = {tau:.2f}. "
           "Rodzina = kampanie z tym samym typem oszustwa i podobną parą spraw.")
joined = {tuple(g) for g in (res or {}).get("joins", [])}
for i, g in enumerate(overview(tau, len(db)), 1):
    hit = tuple(g["members"]) in joined
    label = (f"{'▶ NOWY ARTYKUŁ PASUJE TUTAJ · ' if hit else ''}Kampania {i} · rodzina {g['family']} · "
             f"{g['scam_type']} · {cases_pl(len(g['members']))}: {', '.join(g['members'])}")
    with st.expander(label, expanded=hit):
        for link in g["links"][:6]:
            ev = "; ".join(link["evidence"]) or "brak twardych dowodów"
            st.caption(f"{link['a']} ↔ {link['b']}: podobieństwo {link['score']:.2f} · {ev}")
        for cid in g["members"]:
            show_case(an.case_summary(cid, db[cid]), compact=len(g["members"]) > 3)
