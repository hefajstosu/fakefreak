# Brief: improving the similarity (for the teammate on this task and their Claude Code)

## Starter prompt (paste this into Claude Code at the repo root)
> Read `CLAUDE.md` and `docs/SIMILARITY_BRIEF.md` fully. Your task is to improve `src/ads/similarity.py` so that
> grouping quality improves on the gold labels without breaking the contract described in the brief. First run the
> baseline commands from the brief and show me the numbers, then propose a plan and wait for my go before editing.
> Work on a new branch named `similarity`. Do not touch schemas, prompts or gold labels. Never commit the organiser's
> sample data or anything derived from it.

## What this task is
The similarity decides which ads belong to the same campaign. It is the biggest lever on the project's grouping quality.
The current `score(a, b)` is a deliberately simple **placeholder**; your job is to replace or improve it.
Official task text: the similarity method is completely free (weighted similarity, a small model, a clustering engine...).

## What you may change
- `src/ads/similarity.py` (main work), `config/cluster.yaml` (weights, thresholds), optionally a new `src/ads/embed.py`.
- `src/ads/decision.py` and the slider default in `src/ads/app.py` only to recalibrate thresholds if you change the
  score scale (see the contract).
- `tests/test_similarity.py` and new tests.

Do NOT change without the owner's approval: `schemas/`, `prompts/`, `data/gold/`, the profile format.

## Setup and the private data pack
`pip install -r requirements.txt`, then `python -m pytest tests` (35 tests, synthetic data only, must pass).
To work on real numbers you need the private pack from the project owner (it is derived from the organiser's sample
data and is NOT in git): `data/cases/<id>/profile.json` (plus `variants.json`), and `data/gold/groups.local.json`.
Put them in the same paths. Without the pack only the synthetic tests run. Never commit these files.

## The contract (what the rest of the code expects from `score`)
```python
score(a, b) -> {"score": float in [0,1],              # higher = more likely the same campaign
                "base": float,                         # score before hard-evidence rules
                "contributions": {feature: float},     # per-feature weighted contribution, shown in the demo
                "missing": [feature, ...],             # features that could not be compared (shown in the demo)
                "strong_links": ["shared tracker ID: ...", ...]}   # hard evidence, human readable; may be empty
```
`a` and `b` are profile dicts following `schemas/profile.schema.json`. Callers: `cluster.py`, `evaluate.py`,
`ablation.py`, `robustness.py`, `decision.py`, `app.py`. Rules:
1. **Explainability:** keep `contributions`, `missing` and `strong_links` meaningful; the demo shows them to the jury.
2. **Decision thresholds:** `decision.py` uses score >= `likely` (the sidebar slider, default 0.60), >= 0.80 `confirm`, >= 0.30
   `family`, and treats a non-empty `strong_links` as hard evidence. If your score scale changes, recalibrate these.
3. **Null-aware:** a feature missing on one side must be skipped, not counted as zero (cases may lack an ad, a page or logs).
4. **Demographics never count.** `non_grouping_attributes` must not influence the score (a variant that only changes it
   must score exactly 1.0 against its parent; `python -m ads.ablation` checks this).
5. **No LLM calls and no network inside `score`**; it runs O(n^2) times. Embeddings must be cached.
6. Deterministic, no hidden state. Normalise strings inside similarity (case, accents, aliases such as `tvn24` vs `TVN24`),
   not in the stored profiles.
7. Use only licences compatible with the rules (MIT/Apache/BSD); embedding models must be listed in `docs/LICENSES.md`.

## The development loop (run from `src/`)
```
python -m ads.evaluate --matrix               # ranking constraints, pairwise P/R/F1 vs gold, all pair scores
python -m ads.robustness channels             # switch each feature group off: which evidence matters
python -m ads.robustness degrade              # missing-data tests (ad only / pages only / no traces)
python -m ads.ablation                        # with vs without LLM variants, drift, demographics invariance
python -m pytest ../tests                     # synthetic tests
```
Add `--tau 0.55` etc. where available. Report ALL of these before and after, not one cherry-picked metric.

## Baseline to beat (placeholder similarity, 10 gold cases)
| Metric | Baseline |
|---|---|
| Ranking constraints satisfied | 6 of 7 (the failing one is the health-product group) |
| Pairwise P/R/F1 at tau 0.6, strict gold | 0.33 / 0.67 / 0.44 |
| Pairwise P/R/F1 at tau 0.6, broad gold | 1.00 / 0.46 / 0.63 |
| Channel ablation at tau 0.55: all channels | mean score of true pairs 0.68, strict recall 0.67, broad recall 0.46 |
| ...without infrastructure | true pairs 0.61, strict recall 0.33, broad recall 0.08 |
| ...without scam type + topic | true pairs 0.59, strict recall 0.33, broad recall 0.15 |
| ...without text / entities / props+amounts | recall goes UP (broad recall 0.62 / 0.77 / 0.69) |
| ...without templates | 7 of 7 constraints (the failing one is fixed), broad recall 0.31 |
| Missing data: full case | partner score 0.68, partner recall 0.67 |
| ...ad creative only | partner score 0.41, recall 0.00, but the nearest neighbour is still in the right family |
| ...pages + logs only | partner score 0.65, recall 0.80 |
| Variants in the database | no measurable gain; variants score 0.92 on average against their parent |

AUC is 1.00 everywhere on this small set, so it cannot separate methods: look at recall, margins and the constraints.

## What the ablations suggest (hypotheses to test, not instructions)
1. **Surface features dilute true pairs.** People, products, props and amounts are exactly what scam operators swap, yet a
   difference currently lowers the score. Try treating entity overlap as supporting evidence only (positive-only), so a
   difference does not subtract.
2. **The ad-template feature is too influential** for pairs that share a landing-page template and persuasion tricks. Try
   weighting the landing-page template above the ad template, or using the ad template only when both sides have one.
3. **Semantic text similarity.** Plain bag-of-words is weak. Multilingual embeddings (e.g. `multilingual-e5-small`,
   `bge-m3`) over `canonical_comparison_text` may help, and may finally make the LLM variants useful: rerun
   `python -m ads.ablation` afterwards.
4. **Rarity-weighted evidence.** Weight a shared trace by `log(N / df)`: a rare tracker ID is strong, a common script name
   is not. Keep an ignore list for generic values. Shared platform endpoints currently need at least two shared prefixes.
5. **Calibration.** Per-campaign thresholds (mean minus k standard deviations of variant similarities), or a small
   logistic model on pair features. With 10 cases, use leave-one-case-out and keep the model simple; do not overfit.
6. **Confidence-aware output** for cases seen only as an ad: the decision layer already has a "suggested family" status.

## Guardrails against overfitting and gaming
The gold set is tiny and hand-labelled. Do not tune weights, thresholds or features to individual cases, and do not edit
the gold labels to make a metric pass. Prefer principled changes, check that every channel still contributes in
`robustness channels`, and say which constraints still fail and why. A disappointing honest result is fine and useful.

## Where the relevant code is
```
src/ads/similarity.py   features() extracts comparable features from a profile; score() combines them
src/ads/cluster.py      single-link grouping and assign() for new items (uses score)
src/ads/decision.py     graded decision (duplicate / same content / confirmed / likely / suggested family / new)
src/ads/evaluate.py     gold metrics; src/ads/robustness.py channels + missing data; src/ads/ablation.py variants
src/ads/app.py          Streamlit demo; the sidebar slider is the `likely` threshold
config/cluster.yaml     weights and thresholds read by similarity.py
tests/test_similarity.py  synthetic profile helper `make(...)` for new tests
```

## Working agreement
- Branch `similarity` from `main`; small commits with English messages ending with the Co-Authored-By trailer; open a pull
  request and include a before/after table of the commands above (aggregate numbers only, no sample page text, domains,
  tracker IDs, product names or screenshots).
- Python 3.9, Windows: no same-type nested quotes in f-strings; run module commands from `src/`; print non-ASCII with
  `sys.stdout.reconfigure(encoding="utf-8")`.
- Operational notes (LLM quota, secrets, data policy) are in `CLAUDE.md`. If you need new LLM calls, ask first: the free
  tier allows only about 20 requests per model per day.
