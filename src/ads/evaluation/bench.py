"""How the comparison scales with the size of the database (for docs/DEPLOYMENT.md).

    python -m ads.evaluation.bench [--sizes 100 300 1000]

The database is grown from the profiles in data/cases: copy i of a profile gets its own tracker IDs and a distinct
summary, so copies do not all become one hard-evidence group. Copies repeat strings, so the string caches hit more
often than on N distinct real articles; the "cold" per-pair time is the honest upper bound for those.
Measured: one score(), the full N x N table, the clustering, a first analysis of a new article (whole table and
clustering), another analysis with the database unchanged (campaigns reused) and one after a case was saved (pair
table reused, clustering redone; see analysis/index.py).
"""
import argparse
import copy
import sys
import time
from typing import Dict

from .. import analysis, clustering
from ..database import load_profiles, require_profiles
from ..similarity import score


def grow(base: Dict[str, dict], n: int) -> Dict[str, dict]:
    ids = sorted(base)
    out = {}
    for i in range(n):
        p = copy.deepcopy(base[ids[i % len(ids)]])
        k = i // len(ids)
        ta = p["technical_artifacts"]
        ta["tracker_ids"] = [f"{t}_{k}" for t in ta.get("tracker_ids") or []]
        p["canonical_comparison_text"] = f"{p.get('canonical_comparison_text') or ''} copy {k}"
        out[f"c{i:05d}"] = p
    return out


def timed(fn):
    t = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t


def peak_mb() -> float:
    try:
        import resource  # Unix only
    except ImportError:
        return float("nan")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024  # bytes on macOS, KiB on Linux


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", type=int, nargs="+", default=[100, 300, 1000])
    a = ap.parse_args()
    base = require_profiles(load_profiles())
    ids = sorted(base)
    _, cold = timed(lambda: [score(base[x], base[y]) for x in ids for y in ids])
    _, warm = timed(lambda: [score(base[x], base[y]) for x in ids for y in ids])
    n2 = len(ids) ** 2
    print(f"one score(): {cold / n2 * 1000:.2f} ms cold, {warm / n2 * 1000:.2f} ms with warm string caches")
    print(f"{'N':>6} {'pairs':>9} {'table s':>8} {'cluster s':>9} {'1st analysis s':>14} {'repeat s':>9} "
          f"{'after save s':>12} {'peak MB':>8}")
    for n in a.sizes:
        db = grow(base, n + 2)
        new, new2 = db.pop(f"c{n:05d}"), db.pop(f"c{n + 1:05d}")
        scores, t_table = timed(lambda: clustering.pair_scores(db))
        _, t_cluster = timed(lambda: clustering.cluster(db, clustering.TAU, scores))
        analysis.reset()
        _, t_first = timed(lambda: analysis.compare(new, None, db, clustering.TAU, fingerprints={}))
        _, t_repeat = timed(lambda: analysis.compare(new2, None, db, clustering.TAU, fingerprints={}))
        db["new"] = new  # the analyst saved it; the next article is compared with N + 1 cases
        _, t_saved = timed(lambda: analysis.compare(new2, None, db, clustering.TAU, fingerprints={}))
        print(f"{n:>6} {n * (n - 1) // 2:>9} {t_table:>8.1f} {t_cluster:>9.2f} {t_first:>14.1f} {t_repeat:>9.2f} "
              f"{t_saved:>12.2f} {peak_mb():>8.0f}", flush=True)
        analysis.reset()


if __name__ == "__main__":
    main()
