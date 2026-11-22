# fakefreak: linking scam ads into campaigns

HackNation task "Follow the Fake" (NASK). An ad case (screenshot/video + landing pages + network logs) is turned
into a structured profile by an LLM; profiles are compared and grouped into campaigns by shared narrative,
people, templates, persuasion mechanics and technical traces (tracker IDs, endpoints, domains).
Counterfactual variants (same scam blueprint, swapped surface details) can be generated to test robustness.

## Pipeline
```
raw sample (screenshot / video / saved pages / HAR)
  -> assemble   (src/ads/preprocess/assemble.py)   case_input.json   [schemas/case_input.schema.json]
     (live URLs: src/ads/preprocess/url_scan.py gives page text + the same traces as the HAR parser)
  -> extract    (src/ads/llm/extract.py)           profile.json      [schemas/profile.schema.json]
  -> generate   (src/ads/llm/generate.py)          variants.json     [schemas/variant.schema.json]
  -> similarity (src/ads/similarity.py: score)     score + per-feature contributions + strong links
  -> dedup      (src/ads/dedup.py)                 duplicate of an existing case? (image hash, page text, URL)
  -> clustering (src/ads/clustering/)              campaigns, families / "new campaign"
  -> decision   (src/ads/decision.py)              duplicate / same content / confirmed / likely / suggested family / unconfirmed
  -> explain    (src/ads/explain.py)               why: per-feature breakdown, shared values, evidence, campaign signature
  -> evaluate   (src/ads/evaluate.py, ablation.py) metrics against data/gold
  -> demo       (src/ads/web/, src/ads/app.py)      web panel (default) and Streamlit, both over src/ads/analyze.py
```

## Quick start with Docker (any OS)
Needs Docker Desktop (Windows, macOS) or Docker Engine with the compose plugin (Linux). Tested with Docker 29.9 / Compose 5.7.
```
docker compose up --build        # web panel on http://127.0.0.1:8000 (first build about 2 minutes)
```
- Put the per-case files in `data/cases/` first (see "Sample data"); the container reads and saves cases there.
- Optional `.env` with `GEMINI_API_KEY=...` enables analysing new material. Without it the cases already in `data/` work.
- Streamlit demo as well: `docker compose --profile streamlit up --build` (http://127.0.0.1:8501).
- Any command from "Run" works inside the image: `docker compose run --rm panel python -m ads.evaluate`.
- Ports are published on the host's 127.0.0.1 only, because the panel shows the organiser's samples.

Deployment, configuration, security and measured scaling: `docs/DEPLOYMENT.md`.

## Setup without Docker
Python 3.9 to 3.12 on Windows, macOS or Linux (CI runs the tests on all three with 3.9 and 3.12).
```
python -m venv .venv
.venv\Scripts\activate                 # Windows;  macOS/Linux: source .venv/bin/activate
pip install -r requirements.lock        # pinned versions (tested); requirements.txt lists the direct dependencies
echo GEMINI_API_KEY=your_key > .env     # key from Google AI Studio; .env is gitignored
```
Regenerate the lock after editing `requirements.txt`: `uv pip compile requirements.txt --universal --python-version 3.9 --no-header -o requirements.lock`.
Free-tier Gemini allows about 20 requests per day per model per project. Responses are cached in `.cache/llm`.
By default the client fails over to the models listed in `config/llm.yaml` (`fallback_models`) when one is out of quota;
an explicit `--model` is used as is. Optional heavy components (DeepFace, local Whisper) are in `requirements-optional.txt`.

## Sample data (not in the repo)
The organiser's samples must not be redistributed publicly. Put them in `data/raw/do_udostępnienia/`.
Everything derived from them (`data/cases/*/`, generated fixtures, `data/gold/*.local.json`) is gitignored.
Per case, a `data/cases/<id>/manifest.json` lists the files (see the docstring of `assemble.py`). Set `"transcribe": true` in a manifest to transcribe video audio through the LLM (needs no Whisper; ffmpeg comes from `imageio-ffmpeg`).

## Run
```
cd src
python -m ads.preprocess.assemble --all [--domain-meta] # manifests -> case_input.json (+ public domain metadata)
python -m ads.preprocess.enrich --all --domain-meta     # add page fingerprints / domain metadata to existing cases, no LLM
python -m ads.features                                  # usefulness of every feature against the gold labels
python -m ads.llm.extract ../data/cases/48/case_input.json ../data/cases/48/profile.json
python -m ads.llm.generate 48 --n 3 --k 2               # variants
python -m ads.evaluate --matrix                         # metrics vs gold
python -m ads.ablation                                  # with vs without variants
python -m ads.quality [--sweep]                         # new material vs known campaigns: leave-one-out, 189 variants, must-not-link
python -m ads.robustness channels                       # switch each feature group off in turn
python -m ads.robustness make-degraded --model gemini-3.5-flash-lite   # re-extract reduced inputs (LLM quota)
python -m ads.robustness degrade                        # missing-data tests (ad only / pages only / no traces)
cd .. && streamlit run src/ads/app.py                   # demonstrator
cd src && python -m ads.web.server                      # web panel at http://127.0.0.1:8000: paste a URL, browse the campaigns
python -m ads.explain 1 2                               # why two cases are linked (python -m ads.explain --campaigns)
python -m ads.bench --sizes 100 300 1000                # how comparison time grows with the database
python -m pytest tests                                  # unit tests (synthetic data, no network)
```

## Who owns what
See `docs/CONTRIBUTING.md`. The similarity method is deliberately a replaceable placeholder: anything that
implements `score(profile_a, profile_b) -> {"score", "contributions", "missing", "strong_links"}` plugs into
clustering, evaluation and the demo unchanged.

## Docs
`docs/METHODOLOGY.md` (approach, evaluation, limits), `docs/DEMO.md` (demo script and fallback plan), `docs/CONTRIBUTING.md`,
`docs/LICENSES.md`, `docs/DEPLOYMENT.md` (container, configuration, security, scaling), `docs/DATA_SOURCES.md`
(sources with measured coverage), `docs/CAMPAIGN_PATTERNS.md` (patterns found in the samples).
