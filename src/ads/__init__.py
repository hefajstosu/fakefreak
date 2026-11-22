"""Follow the Fake: link scam ads into campaigns through shared narrative, people, templates and technical traces.

The data flow, and a good order to read the code in:

    paths.py, urls.py      where things live on disk; URL helpers shared by everything below
    preprocess/            material -> case_input.json: assemble.py (manifest), har.py (network logs), url_scan.py
                           (live URL), video.py, transcribe.py, page_fp.py (page structure and image kit),
                           domain_meta.py (public registries), likeness.py (same face, report only), enrich.py
    llm/                   case_input -> profile.json (extract.py); client.py talks to Gemini (cache, failover);
                           generate.py + validate.py make synthetic variants
    sim_functions/         the feature table and its weighted mean; evidence.py states shared traces in words
    similarity.py          score(a, b): the contract every other module uses
    clustering/            pair table -> campaigns (must-links, then average link) -> families
    dedup.py, decision.py  repeat captures; the graded verdict for a new article
    explain/               why a pair scores what it does, why a campaign holds, why an article joined
    database.py            the cases in data/cases: load, save, metadata
    analysis/              one new article end to end (build_case -> analyse -> compare), cached tables
    web/                   the panel: server.py (HTTP), api.py (endpoints), uploads.py, static/ (page and JS modules)
    evaluation/            measurements against data/gold (evaluate, quality, features, robustness, ablation, bench)
"""
