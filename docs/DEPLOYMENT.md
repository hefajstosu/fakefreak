# Deployment, configuration and scaling

How to run the demonstrator anywhere, what it needs, how it keeps its state, how it is secured and how far it scales.
Everything here was checked on the dates and versions given; what was not checked is marked as such.

## 1. Ways to run

| Way | Command | Checked |
|---|---|---|
| Docker Compose (recommended) | `docker compose up --build`, then http://127.0.0.1:8000 | Docker 29.9 / Compose 5.7 on macOS (arm64): builds in about 2 min, panel healthy in about 8 s |
| Plain Docker | `docker build -t fakefreak .` and `docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v "$PWD/data:/app/data" fakefreak` | same |
| Native Python | `pip install -r requirements.lock`, then `cd src && python -m ads.web.server` | Python 3.9.6 and 3.12 on macOS: 97 tests pass, same metrics |
| CI | `.github/workflows/ci.yml`: tests on Ubuntu, Windows and macOS with Python 3.9 and 3.12, then the container build and a smoke test | runs on push; the container job was replayed locally, the OS matrix needs a push to GitHub |

Every command-line tool runs in the same image: `docker compose run --rm panel python -m ads.evaluation.evaluate`
(also `ads.evaluation.quality`, `ads.evaluation.bench`, `ads.explain`, `ads.preprocess.enrich`, `ads.llm.extract`).
The image is multi-platform by construction (official `python:3.12-slim-bookworm` base, wheels for amd64 and arm64);
arm64 was built locally, amd64 is built by CI.

## 2. Configuration

| Setting | Where | Default | Meaning |
|---|---|---|---|
| `GEMINI_API_KEY` | `.env` (optional) | none | LLM key; without it every case already in `data/` works, analysing new material does not |
| `ADS_HOST` / `--host` | env or flag of `ads.web.server` | `127.0.0.1` (image: `0.0.0.0` inside the container) | listen address |
| `ADS_PORT` / `--port` | env or flag; in compose the host port | `8000` | panel port |
| `ADS_UID`, `ADS_GID` | env for `docker compose` | `1000` | container user, set to `$(id -u)` / `$(id -g)` on Linux if saving cases fails |
| model, fallbacks, cache | `config/llm.yaml` | `gemini-3.1-flash-lite`, two fallbacks | provider, models, retries, prompt files |
| weights, ignored values | `config/cluster.yaml` | see file | similarity weights, validated on load (unknown name or negative weight fails fast) |

Switching the LLM provider is one `LLMClient` subclass in `src/ads/llm/client.py` (`_call`) plus `provider:` in
`config/llm.yaml`; caching, retries, JSON repair and failover are provider-independent.

## 3. State, backup and moving to another machine
- **Database = files.** One folder per case in `data/cases/<id>/` (`case_input.json`, `profile.json`, optional
  `variants*.json`, `meta.json` for cases saved from the panel). Back up or move the system by copying `data/`.
  Nothing else is needed to rebuild every score, group and metric: they are recomputed from the profiles.
- **Cache** (`.cache/`, the named volume `ads-cache` in compose): LLM responses keyed by prompt, input and model,
  image/page fingerprints for duplicate detection, public registry answers and the face models. Losing it costs LLM
  and network calls, not data.
- **Uploads** (`data/uploads/<analysis>/`): files sent with an analysis, kept until it is saved or dropped (at most 50
  pending analyses).
- The image contains code, schemas, prompts, config and the public label-only gold file. No sample data and no
  secrets: `.dockerignore` excludes `data/raw`, `data/cases`, `data/uploads`, local gold notes, `.env`, `api.txt` and the cache.

## 4. Security and data protection
- Ports are published on the host's `127.0.0.1` only; the panel shows the organiser's samples, which must not be public.
  The panel has no login. Expose it beyond one machine only behind a reverse proxy with authentication and TLS.
- The container runs as an unprivileged user (uid 1000), not root.
- The live URL scanner follows only http/https, refuses every hop that resolves to a private, loopback, link-local or
  reserved address (no probing of the internal network), never runs JavaScript, and caps time (15 s), size (3 MB per
  response) and hops (8). API request bodies are capped at 200 kB.
- The API key is read from the environment, never logged or returned (`/api/status` only says whether one is set).
- Free-tier Gemini inputs may be used by Google to improve its products. For real, non-sample data use a paid tier or a
  self-hosted model behind the same `LLMClient` interface.

## 5. Cost and the LLM dependency
- One extraction call per new piece of material (plus at most one repair call). Re-analysing the same input, a repeat
  capture (same image or final URL as a known case) and every grouping, metric and comparison cost no LLM call.
- The free tier allows about 20 requests per day per model; the client fails over to the next model in
  `fallback_models` and then reports `QuotaExhausted` clearly. Processing a larger test set in one day needs a paid key.
- Comparison, clustering, duplicate detection and the panel need no network and no GPU.

## 6. Scaling, measured
`python -m ads.evaluation.bench` grows the database from the 10 sample profiles (copies with their own tracker IDs and summary)
and times the comparison. Apple M-series laptop, Python 3.12, one process:

One `score()`: 0.80 ms cold, 0.18 ms with warm string caches (1.9 ms before the changes below).

| N cases | pairs | full table | clustering | first analysis | repeat analysis | analysis after a save | peak memory |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 4 950 | 0.9 s | 0.01 s | 0.9 s | 0.02 s | 0.05 s | 51 MB |
| 300 | 44 850 | 8.0 s | 0.9 s | 8.7 s | 0.06 s | 0.9 s | 147 MB |
| 1000 | 499 500 | 89 s | 48 s | 120 s | 0.19 s | 38 s | 951 MB |

Before these changes every analysis rebuilt the whole table and re-clustered: about 38 s per analysis at N = 200 and,
extrapolated, over 15 minutes at N = 1000. Peak memory includes the benchmark's own full table next to the panel's
cache; the panel alone keeps only score and evidence per pair.

- **First analysis** after a start builds the whole N x N pair table and clusters it. **Repeat** = another article
  with the database unchanged (pair table and campaigns reused, only N new comparisons). **After save** = the
  analyst saved a case, so N new pairs are scored and the campaigns are re-clustered.
- What made this possible (identical scores and groups, checked on the sample profiles): memoised string
  normalisation in the similarity (about 2x faster per pair on distinct profiles, 5x on the benchmark set), a pair table remembered by profile content, and
  campaigns remembered per database state (`analyze.pair_table`, `analyze.campaigns`).
- Copies repeat strings, so the string caches hit more often than on N distinct articles; for those, use the cold
  per-pair time as the upper bound (about 0.8 ms, i.e. about 7 minutes of CPU for the first table of 1000 articles,
  paid once per process start).

**Limits and the next steps, in order of benefit:**
1. **Candidate blocking.** Score only pairs that share a scam type, a tracker, a domain or an endpoint (an inverted
   index over the profiles), plus the top-k by embedding. This turns N x N into roughly N x k; it changes which
   weak pairs are scored at all, so it needs re-checking against the gold labels before it replaces the full table.
2. **Faster average-link.** At N = 1000 clustering is now the slowest step (48 s, paid after each save). The loop
   recomputes group averages every merge (about cubic in N); keeping the
   between-group sums (Lance-Williams update) or a heap of candidate merges makes it quadratic. Needs a tie-breaking
   test to prove the same groups.
3. **Persist the pair table** (SQLite next to `data/cases`) so a restart does not pay for the first analysis again.
4. **Graph store** (for example Neo4j) for the links once analysts need queries across thousands of cases; the
   current JSON files and pair table map directly onto nodes (cases) and edges (scores with evidence).
5. **Queue for LLM extraction** so batches of new material are processed in the background within the rate limits.

The web server is the standard-library threaded HTTP server: enough for a few analysts on one machine. Several
instances can share `data/` read-only; writes (saving a case) should then go through one instance.

## 7. Image size
767 MB (arm64, measured after removing the Streamlit demo, which took about 300 MB). The largest Python packages are
the bundled ffmpeg binary (about 125 MB) and OpenCV (about 90 MB).
