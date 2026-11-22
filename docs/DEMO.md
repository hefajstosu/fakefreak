# Demo script (about 6 minutes) and fallback plan

## Before the session
1. `pip install -r requirements.txt`, put the sample data in `data/raw/` and the per-case files in `data/cases/`
   (see `README.md`), and `GEMINI_API_KEY` in `.env`.
2. `streamlit run src/ads/app.py`, open http://localhost:8501.
3. Sidebar check: "LLM key: found". Leave the model on **auto**. Run one new-material analysis in advance: results are
   cached, so repeating it on stage costs nothing and cannot hit the daily quota.
4. Free-tier quota resets about 09:00 Warsaw time; the demo works without any LLM calls for everything except new material.

## Walkthrough
1. **The idea (30 s).** Many ads look independent; they share traces. We turn each case into a structured profile and
   compare profiles, with every link explained by evidence.
2. **Analyse tab, sample case 48.** Banner: *confirmed* against case 1 with hard evidence (shared platform endpoints).
   Open the neighbours: strong evidence and the features that contributed. Point out that the people and the product
   differ, yet the campaign is linked through infrastructure and template.
3. **Sample cases 1 and 2.** Banner: *same content on another host*. The article is near-identical on a different domain:
   one campaign re-hosted.
4. **Sample case 10.** Banner: *new campaign (unconfirmed)*; nothing close. **Sample case 47:** *possibly related*, treated
   as unconfirmed instead of forced into a group.
5. **Campaigns tab.** Groups at the chosen threshold and the link graph; red edges are hard evidence. Move the sidebar
   threshold to show groups merging. Show the unconfirmed list and the *Confirm this campaign* button if a web case exists.
6. **New material.** Upload an ad screenshot (optionally a landing-page URL or product name) and press *Analyse*.
   Show the extracted profile, the decision banner and the closest cases. Press *Save to database*: it is stored as
   unconfirmed (or as a duplicate if it repeats a known capture).
7. **Evaluation tab.** Ranking constraints satisfied and clustering metrics against the gold labels; be upfront that
   it is a small hand-labelled set and which constraint fails and why (see `docs/METHODOLOGY.md`).
8. **Close (30 s).** Replaceable similarity, ablations show which evidence matters, honest limits.

## If something goes wrong
| Symptom | Cause | What to do |
|---|---|---|
| Sidebar says "LLM key missing" | no key on this machine | stay on sample cases; everything else works |
| "Every configured model is out of free quota" | daily free-tier limit | use sample cases or an already cached analysis; try again after 09:00 Warsaw time |
| URL scan shows "very little text" | page rendered by JavaScript or cloaked | upload a screenshot or saved HTML instead |
| Page does not load | server not running | `streamlit run src/ads/app.py` from the repo root |
| No cases listed | `data/cases/*/profile.json` missing | restore the per-case files (see `README.md`) |

## Container (untested)
`Dockerfile` builds a demo image; mount `data/` at run time (the sample data is never baked in). The build was not
verified because no Docker daemon was available when it was written.
