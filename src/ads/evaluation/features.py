"""How useful is each feature? Measured on the cases in data/cases against the gold labels.

    python -m ads.evaluation.features [--md | --json]

Per feature (every entry of sim_functions.feature_vector, including those with weight 0, so a new feature
can be measured before it counts in the score):
  weight       its weight in the score (config/cluster.yaml)
  coverage     share of cases that have a value for it
  comparable   share of case pairs where both sides have a value (otherwise it is dropped, not scored 0)
  strict / broad / unrelated   mean similarity on gold pairs of the same campaign or template / same scheme only /
               no gold relation
  AUC          probability that a same-campaign pair scores higher on this feature than an unrelated pair
               (0.5 = no information); with only a few strict pairs it is indicative
  false hits   unrelated pairs on which the feature reaches 0.5 or more (where it would mislead)
"""
import argparse
import json
import sys
from itertools import combinations
from typing import Dict, List, Optional

from ..database import load_profiles, require_profiles
from ..sim_functions import feature_vector, load_config
from .gold import BROAD, STRICT, auc, gold_pairs, labelled, load_gold

FALSE_HIT = 0.5


def _mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def feature_table(profiles: Dict[str, dict], gold: dict) -> List[Dict[str, object]]:
    cfg = load_config()
    ids = sorted(labelled(profiles, gold))
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    pairs = list(combinations(ids, 2))
    vectors = {p: feature_vector(profiles[p[0]], profiles[p[1]], cfg["ignore"]) for p in pairs}
    present = {c: {k for k, v in feature_vector(profiles[c], profiles[c], cfg["ignore"]).items()
                   if v is not None} for c in ids}
    names = list(next(iter(vectors.values()))) if vectors else []
    rows = []
    for f in names:
        vals = {p: v[f] for p, v in vectors.items() if v[f] is not None}
        s = [vals[p] for p in strict if p in vals]
        b = [vals[p] for p in broad - strict if p in vals]
        u = [x for p, x in vals.items() if p not in broad]
        rows.append({
            "feature": f, "weight": cfg["weights"].get(f, 0.0),
            "coverage": sum(f in present[c] for c in ids) / len(ids) if ids else 0.0,
            "comparable": len(vals) / len(pairs) if pairs else 0.0,
            "strict": _mean(s), "broad_only": _mean(b), "unrelated": _mean(u),
            "auc": auc(s, u) if s and u else None,
            "false_hits": sum(x >= FALSE_HIT for x in u), "n_unrelated": len(u), "n_strict": len(s),
        })
    return sorted(rows, key=lambda r: (-(r["auc"] if r["auc"] is not None else -1), r["feature"]))


def _fmt(x, nd=2) -> str:
    return "–" if x is None else f"{x:.{nd}f}"


def markdown(rows: List[Dict[str, object]], n_cases: int) -> str:
    out = [f"Feature usefulness on {n_cases} cases (`python -m ads.evaluation.features`). Strict pairs per feature are few "
           "(at most 3 in the sample gold), so AUC is indicative; coverage and false hits are exact.", "",
           "| feature | weight | coverage | comparable pairs | strict | same scheme | unrelated | AUC | false hits |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        out.append(f"| {r['feature']} | {r['weight']:.1f} | {r['coverage']:.0%} | {r['comparable']:.0%} | "
                   f"{_fmt(r['strict'])} | {_fmt(r['broad_only'])} | {_fmt(r['unrelated'])} | {_fmt(r['auc'])} | "
                   f"{r['false_hits']}/{r['n_unrelated']} |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Usefulness of each feature against the gold labels")
    ap.add_argument("--md", action="store_true", help="Markdown table (for METHODOLOGY.md)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    profiles = require_profiles(load_profiles())
    gold = load_gold()
    rows = feature_table(profiles, gold)
    if a.json:
        print(json.dumps(rows, indent=2))
    elif a.md:
        print(markdown(rows, len(labelled(profiles, gold))))
    else:
        print(f"{'feature':<26}{'weight':>7}{'cover':>7}{'pairs':>7}{'strict':>8}{'scheme':>8}{'unrel':>7}{'AUC':>6}"
              f"{'false':>7}")
        for r in rows:
            print(f"{r['feature']:<26}{r['weight']:>7.1f}{r['coverage']:>7.0%}{r['comparable']:>7.0%}"
                  f"{_fmt(r['strict']):>8}{_fmt(r['broad_only']):>8}{_fmt(r['unrelated']):>7}{_fmt(r['auc']):>6}"
                  f"{r['false_hits']:>4}/{r['n_unrelated']}")
        print(f"\nfalse = unrelated pairs scoring >= {FALSE_HIT} on the feature; strict pairs are few: AUC is indicative.")


if __name__ == "__main__":
    main()
