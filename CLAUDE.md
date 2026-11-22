# CLAUDE.md: guide for Claude Code sessions in this repo

## What this project is
HackNation 2026 task "Kolekcjoner fejków / Follow the Fake" (NASK). Scam ads come as **cases** (ad screenshot or video,
landing pages, network logs). An LLM turns each case into a structured **profile**; profiles are compared and
grouped into **campaigns** by shared narrative, people, templates, persuasion tricks and technical traces.
Counterfactual **variants** (same scam blueprint, swapped surface details) are generated to test robustness.
Official goal: link many seemingly independent materials into campaigns through shared traces. It is NOT a fake/real
classifier. The demonstrator is pass/fail (it must exist, looks do not matter). Everything is in Polish-market
context; model output is in English, quoted ad text stays Polish.

## Repo map
```
prompts/extraction.txt        system prompt: case -> profile JSON (closed enums, rules)
prompts/alternatives.txt      system prompt: profile -> N counterfactual variants
schemas/*.schema.json         THE CONTRACTS: case_input, profile, variant (JSON Schema)
src/ads/preprocess/           assemble.py (manifest -> case_input), har.py (HAR -> traces), video.py (contact sheet),
                              transcribe.py (audio -> transcript via LLM), faces.py (DeepFace, optional, not installed)
src/ads/llm/                  client.py (provider-agnostic, disk cache, retries), extract.py, generate.py
src/ads/validate.py           checks generated variants (locked fields, exact k, URLs kept, patches resolve)
src/ads/similarity.py         score(a, b): REPLACEABLE similarity (a teammate is improving it)
src/ads/cluster.py            single-link groups + assign() for new items
src/ads/evaluate.py           ranking constraints + pairwise P/R/F1 vs gold; ablation.py = with/without variants
src/ads/app.py                Streamlit demo
config/*.yaml                 per-track settings (llm, cluster weights, preprocess)
data/gold/groups.json         PUBLIC label-only gold; groups.local.json has the detailed notes (gitignored)
tests/                        synthetic-data tests only (no network, no sample data)
docs/                         CONTRIBUTING.md (track ownership), LICENSES.md, feature list, Polish originals
```
Pipeline: raw sample -> `assemble` -> `case_input.json` -> `extract` -> `profile.json` -> `generate` -> `variants.json`
-> `similarity.score` -> `cluster` -> `evaluate` / demo. Per-case files live in `data/cases/<id>/` (gitignored).

## Run (Windows, Python 3.9, run module commands from `src/`)
```
pip install -r requirements.txt
# .env in the repo root:  GEMINI_API_KEY=...   (gitignored; never print, log or commit it)
cd src
python -m ads.preprocess.assemble --all
python -m ads.llm.extract ../data/cases/48/case_input.json ../data/cases/48/profile.json --model gemini-3.1-flash-lite
python -m ads.llm.generate 48 --n 3 --k 2 --model gemini-3.1-flash-lite
python -m ads.evaluate --matrix
python -m ads.ablation
cd .. && streamlit run src/ads/app.py
python -m pytest tests          # always run before committing
```
Sample data goes in `data/raw/do_udostępnienia/`. Per-case manifests (`data/cases/<id>/manifest.json`) and the
helper scripts in `scripts/` that create them are gitignored; ask the owner for them.

## Rules that matter
1. **Organiser sample data must never be committed or pushed.** Covered by `.gitignore`: `data/raw/`, `data/cases/*/`,
   `data/gold/*.local.json`, `data/refs/`, generated fixtures, `scripts/` helpers. Do not copy page text, domains,
   tracker IDs, sender page names, product names, screenshots or video into tracked files, docs, tests or commit
   messages. Before every commit run `git diff --cached` and look for such strings. Tests use synthetic data only.
2. **Secrets:** `.env` is gitignored. Never echo the key or put it in code, logs, commits or screenshots.
3. **Schemas are contracts.** Changing a field or an enum value needs all three teammates to agree. If you must,
   update schema + prompt + `similarity.py` + tests together.
4. **Do not tune weights or edit gold labels to make metrics look better.** Report failing constraints honestly.
   Gold changes need the owner's approval.
5. **The LLM never identifies people from faces.** Names come from page text/captions or from the (optional) face
   module. Demographics of unidentified people live only in `non_grouping_attributes` and must never influence
   similarity (a demographics-only variant must score exactly 1.0 against its parent; checked in `ablation.py`).
6. **Code, not the model, owns:** technical artifacts, funnel stages, page text in `extracted_text_verbatim`
   (see `extract.py`). Do not make the model re-type long text; it breaks JSON.
7. Variants are synthetic data about real people: keep them internal, never publish, always `synthetic: true`.

## Gemini quota (the main operational trap)
Free tier = about 20 requests per day per model per project; retries and repair calls count. Quota resets about
09:00 Warsaw time. The big flash models (3.5/3.7/3.8) were exhausted on day 1. Models that still answered:
`gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-3-flash-preview`. Responses are cached in `.cache/llm`
(keyed by prompt, input and model); reruns are free. Run API calls sequentially, not 5 at a time (per-minute limits).
Profiles in `data/cases` come from mixed models, so small differences between them are expected.

## Python 3.9 / Windows gotchas
- No same-type nested quotes in f-strings; no `match`; no `X | Y` type unions.
- Print non-ASCII with `sys.stdout.reconfigure(encoding="utf-8")`; the default console is cp1250.
- Paths with Polish letters and very long names exist in the samples; use `os.path` and forward slashes in JSON.
- `python -I` ignores user site-packages and the working directory; do not use it with these modules.
- Git prints LF/CRLF warnings; they are harmless.

## Current status and known issues
- 10 sample cases extracted; 28 variants (case 14 has only 1). Gold: 7 ranking constraints, 6 pass with the placeholder
  similarity (the 47/14/5 health group fails because the ad-template feature is too influential).
- Variants gave no measurable gain over the baseline (tiny dataset, exact-match features). This is a real, reported result.
- Entity strings are not normalised yet (`tvn24` vs `TVN24`): normalise in similarity, not in profiles.
- Not done: face reference set (DeepFace not installed), live URL scan with tracker extraction, image dedup,
  per-campaign thresholds, ad-library scheduler.
- The teammates' earlier analysis (entity masking, rarity weighting, per-campaign thresholds, hierarchy) is in git
  history: `git show 8837ebb:analiza_algorytmu.md`.

## Working style
Branch per task, small commits, English commit messages ending with the Co-Authored-By trailer. Keep tests passing.
Prefer extending `config/*.yaml` and the schemas over hard-coding. Ask before pushing to `main`.
