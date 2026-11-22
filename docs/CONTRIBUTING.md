# Working together on fakefreak

Three tracks, one directory set each, one shared contract layer. See the plan for the full reasoning.

| Track | Owns | Produces | Consumes |
|---|---|---|---|
| A: data and preprocessing | `src/ads/preprocess/`, `data/cases/`, `data/refs/`, `config/preprocess.yaml` | `case_input.json` | raw samples |
| B: LLM layer | `src/ads/llm/`, `src/ads/validate.py`, `prompts/`, `config/llm.yaml` | `profile.json`, variants | `case_input.json` |
| C: similarity and evaluation | `src/ads/similarity.py`, `src/ads/sim_functions/`, `src/ads/clustering/`, `src/ads/evaluate.py`, `data/gold/`, `config/cluster.yaml` | scores, groups, metrics | profiles and variants |

Shared and changed only by a pull request that all three approve: `schemas/`, `docs/`, `requirements.txt`.

## Rules
1. One branch per track (`track-a`, `track-b`, `track-c`), merged into `main` by pull request. Do not edit files owned by another track; ask them or open a PR they approve.
2. The contracts are `schemas/case_input.schema.json`, `profile.schema.json`, `variant.schema.json`. Validate everything you produce or consume against them (`jsonschema`). Changing a field or an enum value needs all three approvals.
3. Work against the fixtures in `tests/fixtures/` until your upstream track delivers real data.
4. `requirements.txt` is append-only; add one line per dependency in its own PR.
5. Secrets (API keys) live in `.env`, never in the repo. Each person uses their own key.

## Organiser data (important)
The sample cases came from the organiser (shared with participants, e.g. on the HackNation Discord). Treat them as not for public redistribution, as the team's earlier `.gitignore` already did.
- Gitignored: `data/raw/`, `dane/`, `manual.pdf`, generated fixtures (`tests/fixtures/case_input/`, `tests/fixtures/profiles/`), `data/cases/*/`, and `data/gold/*.local.json`.
- Get the sample data from the organiser's channel and put it in `data/raw/do_udostępnienia/`, then get `scripts/build_fixtures.py` from the author (it is gitignored because it holds hand-written annotations with sample-derived names and ad headlines) and run it to create the fixtures locally.
- `data/gold/groups.json` is the public version (labels only). The detailed notes are in `groups.local.json`; ask the author.
- Before committing, check that you are not adding page text, domains, tracker IDs, page names or screenshots from the samples.

## Sync points
1. After Day 0: the tracks start independently.
2. Sync 1: Track A delivers three real cases, Track B turns them into profiles, Track C runs the first real baseline.
3. Sync 2: all ten profiles and the baseline exist; variants are generated and compared.
4. Final: tuning, the classify entry point, the demonstrator.
