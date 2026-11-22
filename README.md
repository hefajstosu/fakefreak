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
  -> cluster    (src/ads/cluster.py)               groups / "new campaign"
  -> evaluate   (src/ads/evaluate.py, ablation.py) metrics against data/gold
  -> demo       (src/ads/app.py)                   Streamlit
```

## Setup
```
python -m venv .venv && .venv\Scripts\activate        # Python 3.9+
pip install -r requirements.txt
echo GEMINI_API_KEY=your_key > .env                   # key from Google AI Studio; .env is gitignored
```
Free-tier Gemini allows about 20 requests per day per model per project. Responses are cached in `.cache/llm`.
If a model's quota is exhausted, pass another with `--model` (e.g. `gemini-3.8-flash`, `gemini-3.1-flash-lite`).

## Sample data (not in the repo)
The organiser's samples must not be redistributed publicly. Put them in `data/raw/do_udostępnienia/`.
Everything derived from them (`data/cases/*/`, generated fixtures, `data/gold/*.local.json`) is gitignored.
Per case, a `data/cases/<id>/manifest.json` lists the files (see the docstring of `assemble.py`). Set `"transcribe": true` in a manifest to transcribe video audio through the LLM (needs no Whisper; ffmpeg comes from `imageio-ffmpeg`).

## Run
```
cd src
python -m ads.preprocess.assemble --all                 # manifests -> case_input.json
python -m ads.llm.extract ../data/cases/48/case_input.json ../data/cases/48/profile.json
python -m ads.llm.generate 48 --n 3 --k 2               # variants
python -m ads.evaluate --matrix                         # metrics vs gold
python -m ads.ablation                                  # with vs without variants
python -m ads.robustness channels                       # switch each feature group off in turn
python -m ads.robustness make-degraded --model gemini-3.5-flash-lite   # re-extract reduced inputs (LLM quota)
python -m ads.robustness degrade                        # missing-data tests (ad only / pages only / no traces)
cd .. && streamlit run src/ads/app.py                   # demonstrator
python -m pytest tests                                  # unit tests (synthetic data, no network)
```

## Who owns what
See `docs/CONTRIBUTING.md`. The similarity method is deliberately a replaceable placeholder: anything that
implements `score(profile_a, profile_b) -> {"score", "contributions", "missing", "strong_links"}` plugs into
clustering, evaluation and the demo unchanged.

## Licences
See `docs/LICENSES.md`.
