# Working together on fakefreak

## Who owns what
| Track | Owns | Produces |
|---|---|---|
| A: material | `src/ads/preprocess/`, `src/ads/urls.py` | `case_input.json`, page fingerprints, domain facts |
| B: LLM | `src/ads/llm/`, `prompts/`, `config/llm.yaml` | `profile.json`, variants |
| C: method | `src/ads/similarity.py`, `sim_functions/`, `clustering/`, `explain/`, `evaluation/`, `data/gold/`, `config/cluster.yaml` | scores, groups, explanations, metrics |

Shared, changed only with all three agreeing: `schemas/` (the contracts), `docs/`, `requirements.txt`. The panel
(`analysis/`, `database.py`, `web/`) only calls the three tracks. `.github/CODEOWNERS` mirrors this table.

## Rules
1. **The organiser's samples are never committed** (`.gitignore` covers `fakes`, `data/raw/`, `data/cases`,
   `data/uploads/`, `data/gold/*.local.json`, `scripts/`). No page text, domains, tracker IDs, page names, people or
   product names, screenshots or video in tracked files, tests or commit messages; check `git diff --cached`.
   Per-case manifests and the scripts that build them are shared privately.
2. **Schemas are contracts.** A field or enum change updates schema, prompt, `sim_functions/` and tests together.
3. **No tuning to the gold labels.** Fix a new weight by analogy before measuring, measure with the commands below, keep
   the change only if it does not mislead, and report the numbers either way. Gold changes need the owner.
4. **Secrets** live in `.env`, never in the repository; each person uses their own key.
5. One branch per change, small commits, tests passing (`python -m pytest`), pull request into `main`.

## Measuring a change to the method (from `src/`)
```
python -m ads.evaluation.evaluate          # ranking constraints, campaigns and families against the gold labels
python -m ads.evaluation.quality --sweep   # new material against known campaigns, for tau 0.30 .. 0.80
python -m ads.evaluation.features          # coverage, AUC and false hits of every feature
python -m ads.explain A B                  # why one pair scores what it does
```
`score(a, b)` must keep returning `{"score", "contributions", "missing", "strong_links"}`: clustering, explanations,
the panel and the evaluation depend on it.
