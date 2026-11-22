# CLAUDE.md: guide for Claude Code sessions in this repo

> **Working on the similarity? Read `docs/SIMILARITY_BRIEF.md` first** (contract, baseline numbers, commands, hypotheses, guardrails).
> Similarity logic lives in `src/ads/sim_functions/`, grouping logic in `src/ads/clustering/`; `similarity.py` is a thin wrapper.

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
                              transcribe.py (audio -> transcript via LLM), url_scan.py (live URL -> text + traces), faces.py (DeepFace, optional, not installed)
src/ads/llm/                  client.py (provider-agnostic, disk cache, retries), extract.py, generate.py
src/ads/validate.py           checks generated variants (locked fields, exact k, URLs kept, patches resolve)
src/ads/similarity.py         score(a, b): thin wrapper, the contract callers use; calls sim_functions (no logic of its own)
src/ads/sim_functions/        THE similarity (a teammate owns it): attributes.py (per-attribute similarities), primitives.py,
                              normalize.py, aggregate.py (weights, null-aware weighted mean), compare.py (compare_all,
                              similarity_vector, compare_to_variants), embeddings.py (optional E5), evidence.py (strong_links)
src/ads/clustering/           ALL grouping logic: pairs.py (N x N pair scores, variants), evidence.py (must-link rules),
                              linkage.py (average-link cluster()), families.py (hierarchy(): campaigns -> families),
                              assign.py (place a new article), variants.py (load_variants)
src/ads/paths.py              repository locations (REPO, DATA, CASES, CONFIG, ...) and gold_file(); import paths from here
src/ads/dedup.py              duplicate detection: image dHash, page-text hash + near-dup sketch, final URL
src/ads/decision.py           graded decision: duplicate / same_content / confirmed / likely / suggested_family / new_unconfirmed
                              (each result names its "rule"; must-link evidence with any case confirms, as in clustering)
src/ads/explain.py            reporting only: why a pair scores what it does, why a campaign holds, why an article joined;
                              used by the web panel (Dlaczego?, graph tab, report) and `python -m ads.explain`
src/ads/robustness.py         channel ablation + missing-data tests
src/ads/evaluate.py           ranking constraints + pairwise P/R/F1 vs gold; ablation.py = with/without variants
src/ads/app.py                Streamlit demo
src/ads/web/                  web panel: server.py (stdlib JSON API on 127.0.0.1) + static/ page; logic in analyze.py (no UI, tested)
config/*.yaml                 per-track settings (llm, cluster weights, preprocess)
data/gold/groups.json         PUBLIC label-only gold; groups.local.json has the detailed notes (gitignored)
tests/                        synthetic-data tests only (no network, no sample data)
docs/                         METHODOLOGY.md, DEMO.md, CONTRIBUTING.md (track ownership), LICENSES.md, feature list, Polish originals
Dockerfile, docker-compose.yml demo image (web panel default, Streamlit profile), tested; requirements.lock = pinned deps;
                              requirements-optional.txt = heavy extras; .github/workflows/ci.yml = tests on 3 OSes + container
src/ads/bench.py              scaling benchmark; docs/DEPLOYMENT.md = container, config, security, measured scaling
archive/                      old local prototype (algorytm.py and its outputs), gitignored; not part of the pipeline
```
Pipeline: raw sample -> `assemble` -> `case_input.json` -> `extract` -> `profile.json` -> `generate` -> `variants.json`
-> `similarity.score` (sim_functions) -> `clustering` -> `evaluate` / demo. Per-case files live in `data/cases/<id>/` (gitignored).

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
docker compose up --build       # same panel in a container (http://127.0.0.1:8000), data/ mounted
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
   update schema + prompt + `sim_functions/` + tests together.
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
The client fails over across `fallback_models` (config/llm.yaml) when a model is out of quota and raises `QuotaExhausted`
(no retries) when all are; an explicit `--model` disables failover. The demo shows a clear message and keeps sample cases working.
Profiles in `data/cases` come from mixed models, so small differences between them are expected.

## How similarity and grouping work now
- `score(a, b)` = `sim_functions.compare_all`: weighted, null-aware mean over per-attribute similarities (a feature missing on
  one side is dropped, not 0). Technical anchors (tracker IDs, redirect domains, DOM/form clues, sponsoring page) are part of
  the score through their own weights. `strong_links` (from `sim_functions/evidence.py`) is evidence REPORTING only: it never
  changes the number. `base` equals `score`. A shared tracker therefore no longer lifts a score to 0.9.
- Grouping (`ads.clustering`) works on the N x N table of `score()` results, not on the per-attribute matrices:
  1. hard evidence is a must-link (shared tracker ID, >= 2 shared endpoint prefixes, same sponsoring page; shared domains and
     files are NOT must-links), merged first;
  2. average-link merging of the rest while the MEAN score between two groups >= tau (single link chained weak bridges);
  3. `hierarchy()` groups campaigns into families (same scam type, some member pair >= `family_tau`);
  4. `assign()` joins a new article to a group on hard evidence with a member or mean score >= tau.
- Synthetic variants are extra comparisons only: pass `variants={case_id: [profiles]}` (from `clustering.load_variants`) and a real
  article's score becomes the best of score(a, b), a vs each variant of b, each variant of a vs b. A variant is never a node
  or group member and variants are never compared with each other. `variant_gate` (default off; try 0.15) skips variant
  comparisons for pairs below it that share no hard evidence. Result key `via_variant` ("a:<i>"/"b:<i>"/None) says where a score
  came from. Wired into the demo (sidebar checkbox) and `python -m ads.evaluate --variants [--gate 0.15]`; `ablation --gate`
  reports what the gate would lose. Variant files stay in gitignored `data/cases/*/`.
- Weights, anchor weights and `ignore_values` come from `config/cluster.yaml` via `sim_functions/config.py` (validated: an unknown
  weight name or a negative weight raises). Keys missing from the file keep the defaults in `aggregate.py`. `thresholds` in the
  file are not read by any code yet.
- Not yet used by `score()`: embeddings (`embeddings.E5Embedder`) and rarity weighting (`anchor_stats`); `compare_all` supports both.
- Thresholds were written for the old score scale. The top gold pair now scores about 0.67, so the demo slider (0.60) and the 0.80
  "confirmed" cut-off in `decision.py` probably need recalibrating. `decision.py` and the demo do not use `hierarchy()` yet.

## Python 3.9 / Windows gotchas
- No same-type nested quotes in f-strings; no `match`; no `X | Y` type unions.
- Print non-ASCII with `sys.stdout.reconfigure(encoding="utf-8")`; the default console is cp1250.
- Paths with Polish letters and very long names exist in the samples; use `os.path` and forward slashes in JSON.
- `python -I` ignores user site-packages and the working directory; do not use it with these modules.
- Git prints LF/CRLF warnings; they are harmless.

## Current status and known issues
- 10 sample cases extracted; 28 variants generated earlier (case 14 has only 1), but `variants.json` files are absent on some machines.
  Gold: 7 ranking constraints; with `sim_functions` + `clustering` all 7 pass (the 47/14/5 health group failed with the old
  placeholder). Pairwise at tau 0.6: strict P/R/F1 0.33/0.67/0.44, broad 1.00/0.46/0.63 (average-link needs the must-link rule:
  without it broad recall is 0.08 at 0.6). The variant gate and variant wiring are not yet measured (no variants locally).
- Variants gave no measurable gain over the baseline (tiny dataset, exact-match features). This is a real, reported result.
- Findings from `ads.robustness` (measured on the OLD placeholder similarity, NOT re-run on `sim_functions`; tau 0.55, 10 gold cases; weights are guesses, so treat as indicative):
  * Infrastructure and scam type + topic carry the grouping: switching either off drops recall sharply.
  * Switching off text, entities or props/amounts RAISES recall: surface features dilute pairs that share a template or
    infrastructure, although surface elements are exactly what operators swap. A better similarity should use entity overlap
    as supporting evidence, not let differences subtract. Switching off templates fixes the failing gold constraint.
  * Missing data: pages + logs only keep about 80% of partner recall; the ad creative alone scores below the threshold
    (recall 0) yet its top-1 neighbour is still in the right family. Decide per evidence level: suggest a family when
    confidence is low, confirm a campaign only with strong evidence. From the ad alone, scam type is unreliable for some
    cases because it depends on where the funnel ends.
  * Caveat: reduced-input extractions used gemini-3.5-flash-lite, baseline profiles come from other models.
- Entity strings are normalised inside `sim_functions/normalize.py` (case, accents, punctuation), not in the profiles.
- Live URL scan is done (`url_scan.py`): redirect chain, tracker IDs (also from config blobs and first-party scripts),
  form endpoints, first-party files, and platform endpoint paths (`api:/api/v1/...`) read from up to 3 first-party
  scripts. Blocks private addresses; does NOT run JavaScript, so pixels injected only at runtime are missed.
  Offline replay on the saved sample pages recovered the same pixel and the same platform endpoints as the recorded
  logs. Shared platform endpoints prove a shared landing-page tool, not necessarily one operator; similarity needs
  >=2 shared endpoint prefixes before treating them as evidence. The demo uses the scan for the URL field.
- Duplicates and graded decisions are in (`dedup.py`, `decision.py`, used by the demo). Image dHash threshold is 6 of 64
  bits: on the sample images the closest unrelated pair was 9 bits apart, so no false positives, but screenshots of the
  same ad at different scroll positions differ by 17-36 bits and are NOT caught (they fall through to similarity).
  Saved web cases get `meta.json` (`status: unconfirmed`, or `duplicate_of`); duplicates are excluded from the database.
- Not done: face reference set (DeepFace not installed), per-campaign thresholds, ad-library scheduler.
- The teammates' earlier analysis (entity masking, rarity weighting, per-campaign thresholds, hierarchy) is in git
  history: `git show 8837ebb:analiza_algorytmu.md`.

## Working style
Branch per task, small commits, English commit messages ending with the Co-Authored-By trailer. Keep tests passing.
Prefer extending `config/*.yaml` and the schemas over hard-coding. Ask before pushing to `main`.
