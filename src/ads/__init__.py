"""Follow the Fake: link scam ads into campaigns through shared narrative, people, templates and technical traces.

The data flow, and a good order to read the code in:

    paths.py               where things live on disk (data/cases, config, prompts, schemas, .cache)
    preprocess/            material -> case_input.json: assemble.py drives video.py, transcribe.py and har.py;
                           url_scan.py does the same for a live URL
    llm/                   case_input -> profile.json (extract.py); client.py talks to Gemini (cache, failover);
                           generate.py + validate.py make optional synthetic variants
    similarity.py          score(a, b) in [0, 1] from the 21 per-feature similarities in sim_functions/
    clustering/            N x N pair scores -> campaigns (must-link, then average link) -> families
    dedup.py, decision.py  repeat captures; the graded decision for a new case
    analyze.py             one new article end to end: build_case -> analyse (profile + compare); used by both UIs
    web/, app.py           the web panel (stdlib server + static page) and the Streamlit demo
    evaluate.py            metrics against data/gold; ablation.py (variants) and robustness.py (channels, missing data)
"""
