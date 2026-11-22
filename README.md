# fakefreak: linking scam ads into campaigns

HackNation task "Follow the Fake" (NASK). An ad case (screenshot or video, landing pages, network logs) becomes a
structured profile (an LLM for the content, code for the technical traces); profiles are compared feature by feature
and grouped on two levels: campaigns (one operator: shared tracker, ad campaign ID, certificate, or the same content)
and families of campaigns (one scheme or one tool). Every link comes with its reasons.

## Pipeline
```
material (screenshot, video, saved page, HAR log, live URL)
  -> preprocess/   case_input.json   traces, page fingerprints, public domain metadata   [schemas/case_input]
  -> llm/extract   profile.json      narrative, people, templates, persuasion             [schemas/profile]
  -> similarity    score(a, b)       weighted mean of the features present on both sides, plus evidence in words
  -> clustering/   campaigns, families
  -> decision      duplicate / same content / confirmed / likely / suggested family / new
  -> explain/      why: shares of the score, shared values, evidence, campaign signature
  -> web/          the panel (analysis/ does one article end to end)
  -> evaluation/   measured against data/gold
```
`src/ads/__init__.py` maps every package; `docs/METHODOLOGY.md` explains the method and its measurements.

## Quick start with Docker (any OS)
Needs Docker Desktop (Windows, macOS) or Docker Engine with the compose plugin (Linux).
```
docker compose up --build        # the panel on http://127.0.0.1:8000
```
- Put the per-case files in `data/cases/` first (see "Sample data"); the container reads and saves cases there.
- An optional `.env` with `GEMINI_API_KEY=...` enables analysing new material; without it the cases in `data/` work.
- Any command below runs in the image: `docker compose run --rm panel python -m ads.evaluation.evaluate`.
- Ports are published on the host's 127.0.0.1 only, because the panel shows the organiser's samples.

Container, configuration, security and measured scaling: `docs/DEPLOYMENT.md`.

## Setup without Docker
Python 3.9 to 3.12 on Windows, macOS or Linux (CI runs the tests on all three with 3.9 and 3.12).
```
python -m venv .venv
.venv\Scripts\activate                 # Windows;  macOS/Linux: source .venv/bin/activate
pip install -r requirements.lock        # pinned versions; requirements.txt lists the direct dependencies
echo GEMINI_API_KEY=your_key > .env     # key from Google AI Studio; .env is gitignored
```
Free-tier Gemini allows about 20 requests per day per model per project. Responses are cached in `.cache/llm`, and the
client fails over to the models in `config/llm.yaml` (`fallback_models`) when one is out of quota.

## Sample data (not in the repo)
The organiser's samples must not be redistributed. Everything derived from them (`data/cases/`, `data/uploads/`,
`data/gold/*.local.json`) is gitignored. Per case, `data/cases/<id>/manifest.json` lists its files with paths relative
to `data/` (see the docstring of `src/ads/preprocess/assemble.py`); `"transcribe": true` transcribes video audio
through the LLM.

## Run (from `src/`)
```
python -m ads.web.server                                # the panel: http://127.0.0.1:8000 (URL, text or files)
python -m ads.preprocess.assemble --all [--domain-meta] # manifests -> case_input.json
python -m ads.llm.extract ../data/cases/48/case_input.json ../data/cases/48/profile.json
python -m ads.preprocess.enrich --all --domain-meta     # page fingerprints and domain facts for existing cases, no LLM
python -m ads.llm.generate 48 --n 3 --k 2               # synthetic variants
python -m ads.explain 1 2                               # why two cases are linked (--campaigns: every campaign)
python -m ads.evaluation.evaluate --matrix              # two-level metrics against the gold labels
python -m ads.evaluation.quality [--sweep]              # new material against known campaigns
python -m ads.evaluation.features                       # usefulness of every feature
python -m ads.evaluation.robustness channels            # feature groups switched off (degrade: material removed)
python -m ads.evaluation.ablation                       # with and without the synthetic variants
python -m ads.evaluation.bench                          # comparison time against database size
python -m ads.preprocess.likeness --download --gold     # same face across materials (local, no names)
cd .. && python -m pytest                               # tests: synthetic data, no network
```

## Docs
`docs/METHODOLOGY.md` (method, measurements, limits), `docs/DATA_SOURCES.md` (sources with measured coverage),
`docs/CAMPAIGN_PATTERNS.md` (patterns found), `docs/DEMO.md` (demo script), `docs/DEPLOYMENT.md`,
`docs/CONTRIBUTING.md` (who owns what, rules), `docs/LICENSES.md`.
