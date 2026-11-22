# CLAUDE.md: guide for Claude Code sessions in this repo

## What this project is
HackNation 2026 task "Kolekcjoner fejków / Follow the Fake" (NASK). Scam ads come as **cases** (ad screenshot or video,
landing pages, network logs). Code extracts the technical traces, an LLM the content; the resulting **profiles** are
compared and grouped into **campaigns** (one operator) and **families** of campaigns (one scheme or tool), with every link
explained. Synthetic **variants** (same scheme, swapped surface details) are evaluation material. It is NOT a fake/real
classifier. The panel is pass/fail for the jury (looks do not matter). Polish-market context; model output in English,
quoted ad text stays Polish; the panel is in Polish.

## Repo map (read `src/ads/__init__.py` for the package map)
```
prompts/, schemas/            LLM prompts; THE CONTRACTS case_input, profile, variant (JSON Schema)
src/ads/preprocess/           material -> case_input: assemble, har, url_scan, video, transcribe, page_fp, domain_meta,
                              likeness (same face, report only), enrich (code-owned fields of existing cases, no LLM)
src/ads/llm/                  client (Gemini, cache, failover), extract, generate + validate (variants)
src/ads/sim_functions/        THE similarity: features.py (feature table, compare_all), attributes.py, primitives.py,
                              normalize.py, evidence.py (strong_links), config.py (config/cluster.yaml)
src/ads/similarity.py         score(a, b): the contract everything else calls
src/ads/clustering/           pairs, evidence (must-link / family-link rules), linkage, families, assign, variants
src/ads/explain/              reporting only: pair, campaign, joins (assignment, decision_reasons); python -m ads.explain
src/ads/analysis/             one new article: case (build_case), compare (analyse), index (cached tables), views
src/ads/database.py           data/cases: load_profiles, case_meta, first_image, save_case
src/ads/web/                  server.py (HTTP), api.py (endpoints), uploads.py; static/index.html, style.css, js/*.js
src/ads/evaluation/           gold.py + evaluate, quality, features, robustness, ablation, bench (python -m ads.evaluation.X)
config/                       cluster.yaml (weights, ignore list, supporting features), llm.yaml (models, fallbacks)
data/gold/groups.json         PUBLIC label-only gold; groups.local.json has the detailed notes (gitignored)
tests/                        synthetic data only (factory.py builds profiles); pytest.ini sets the paths
docs/                         METHODOLOGY, DATA_SOURCES, CAMPAIGN_PATTERNS, DEMO, DEPLOYMENT, CONTRIBUTING, LICENSES
Dockerfile, docker-compose.yml the panel image (tested); requirements.lock pinned deps; .github/workflows/ci.yml
```

## Run (from `src/`; Python 3.9 on Windows is the team's main setup)
```
pip install -r ../requirements.lock      # .env in the repo root: GEMINI_API_KEY=... (never print, log or commit it)
python -m ads.web.server                 # the panel on http://127.0.0.1:8000
python -m ads.evaluation.evaluate        # also: quality [--sweep], features, robustness channels, ablation, bench
python -m ads.preprocess.enrich --all --domain-meta   # after assemble, for page fingerprints and domain facts
cd .. && python -m pytest                # always before committing
```
Raw samples live outside git (`fakes/` or `data/raw/` next to `data/`); manifests point to them relative to `data/`.

## Rules that matter
1. **Organiser sample data must never be committed or pushed** (`.gitignore` covers it). No page text, domains, tracker
   IDs, page names, product or people names, screenshots or video in tracked files, docs, tests or commit messages.
   Before every commit run `git diff --cached` and look for such strings.
2. **Secrets:** `.env` is gitignored. Never echo the key or put it in code, logs, commits or screenshots.
3. **Schemas are contracts.** A field or enum change needs all three teammates; update schema, prompt, `sim_functions/`
   and tests together. Code-owned optional fields (`technical_artifacts.page_fingerprints`) are kept out of the prompt
   (`extract.CODE_ONLY_TECH_KEYS`) so cached LLM answers stay valid.
4. **Do not tune weights or edit gold labels to make metrics look better.** Fix weights by analogy before measuring,
   report failures honestly. Gold changes need the owner's approval.
5. **No face identification.** The LLM never identifies people from faces; names come from text, captions and
   transcripts. `likeness.py` compares faces without names, only locally (`.cache/likeness`), and is not scored.
   Demographics of unidentified people never influence similarity (checked in `evaluation/ablation.py`).
6. **Code, not the model, owns** technical artifacts, page fingerprints, domain facts, funnel stages and page text in
   `extracted_text_verbatim` (see `llm/extract.py`).
7. Variants are synthetic data about real people: internal only, never published.

## Gemini quota (the main operational trap)
About 20 requests per day per model per project on the free tier; retries and repairs count; resets about 09:00 Warsaw
time. Models that answered: `gemini-3.1-flash-lite` (default), `gemini-3.5-flash-lite`, `gemini-3-flash-preview`.
Answers are cached in `.cache/llm` (keyed by prompt, input and model); run calls sequentially. The client fails over
across `fallback_models` and raises `QuotaExhausted` when all are out; an explicit `--model` disables failover.

## How similarity and grouping work
- `score(a, b)`: weighted mean over the features present on both sides (`sim_functions/features.py`); a feature missing
  on a side, technical traces included, is dropped, not scored 0. Weight-0 features (logos, domain facts) are computed and
  explained only. `strong_links` states shared traces in words and never changes the number.
- Campaigns (`clustering`): must-links first (shared tracker ID, sponsoring page, ad campaign ID, domains on one
  certificate, or a pair scoring >= 0.80), then average link while the MEAN score between groups >= tau (0.6).
- Families: same scam type and a member pair >= 0.30, or family evidence (>= 2 shared platform endpoints, >= 2 identical
  page images, the same own tracking template): a shared tool or kit, not proof of one operator.
- `decision.decide` uses the same rules (every result names its `rule`); `explain/` reproduces every number.
- Variants are extra comparisons in `pair_scores` only (`via_variant` says where a score came from); never grouped.

## Current status
- 10 sample cases, 189 fresh variants. Tau 0.6: campaigns vs strict gold P/R/F1 1.00/0.33/0.50, families vs broad gold
  1.00/0.85/0.92, 6 of 7 ranking constraints (sim(47,14) < sim(47,5) fails). `evaluation.quality`: campaign purity 1.00,
  no false joins anywhere, families correct 0.90-1.00. Numbers and their history: `docs/METHODOLOGY.md` section 10.
- Open: same-template pairs 48-61 and 14-47 are not linked as campaigns by content alone; case 14 misses its family
  (scores 0.25-0.29 < 0.30). Next lever: better text similarity (only stem overlap today).
- Duplicates: image dHash (6 of 64 bits), page-text hash and sketch, final URL; screenshots at other scroll positions are
  not caught. Saved panel cases get `meta.json` (`unconfirmed` or `duplicate_of`).
- Not done: ad-library scheduler (needs a Meta API token), per-campaign thresholds.

## Python 3.9 / Windows gotchas
- No `match`, no `X | Y` type unions, no same-type nested quotes in f-strings.
- Print non-ASCII with `sys.stdout.reconfigure(encoding="utf-8")`; the default console is cp1250.
- Sample paths contain Polish letters and very long names; use `os.path` and forward slashes in JSON.
- Git prints LF/CRLF warnings; they are harmless.

## Working style
Branch per task, small commits, English commit messages ending with the Co-Authored-By trailer. Keep tests passing.
Prefer extending `config/*.yaml` and the schemas over hard-coding. Ask before pushing to `main`.
