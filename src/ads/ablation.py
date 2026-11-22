"""Ablation: does adding counterfactual variants to the database help grouping?

    python -m ads.ablation [--taus 0.5,0.6,0.7] [--gold data/gold/groups.local.json]

Leave-one-case-out. For each test case X the database contains the originals of all OTHER cases
and, in the "with variants" condition, also their variants (never X's own, so no leakage).
A database case Y is scored against X as max over Y's original and its variants. Metrics, averaged
over test cases that have gold partners:
  * partner recall at tau: share of X's strict gold partners with score >= tau
  * false joins at tau: number of cases outside X's broad gold partners with score >= tau
  * pairwise ranking accuracy: P(score(X, partner) > score(X, non-partner))
Also reported: similarity of each variant to its own parent (semantic drift check) and the
demographics-invariance check (variants that changed only non-grouping traits must score 1.0
against the parent).
"""
import argparse
import json
import sys
from typing import Dict

from .evaluate import gold_pairs, load_profiles
from .paths import gold_file
from .clustering.pairs import best_score
from .clustering.variants import load_variants
from .similarity import score

DEMO_SLOT = "non_grouping_attributes.unidentified_people_demographics"


def partners(gold: dict, cid: str, levels) -> set:
    return {b if a == cid else a for a, b in gold_pairs(gold, levels) if cid in (a, b)}


def run(profiles, variants, gold, taus, gate=None, stats=None):
    strict_lv, broad_lv = {"same_campaign", "same_template"}, {"same_campaign", "same_template", "same_scheme"}
    rows = {"without": [], "with": []}
    for x in profiles:
        sp, bp = partners(gold, x, strict_lv) & set(profiles), partners(gold, x, broad_lv) & set(profiles)
        if not sp:
            continue
        others = [y for y in profiles if y != x]
        s_wo = {y: score(profiles[x], profiles[y])["score"] for y in others}
        s_w = {y: best_score(profiles[x], profiles[y], None, variants.get(y), gate, stats)["score"] for y in others}
        for cond, sc in (("without", s_wo), ("with", s_w)):
            neg = [y for y in others if y not in bp]
            wins = [sc[p] > sc[n] for p in sp for n in neg]
            rows[cond].append({"case": x, "sc": sc, "sp": sp, "neg": neg,
                               "rank_acc": sum(wins) / len(wins) if wins else None})
    return rows


def summarize(rows, taus):
    out = {}
    for cond, rs in rows.items():
        o = {"rank_acc": sum(r["rank_acc"] for r in rs if r["rank_acc"] is not None) / len(rs)}
        for t in taus:
            o[f"recall@{t}"] = sum(sum(r["sc"][p] >= t for p in r["sp"]) / len(r["sp"]) for r in rs) / len(rs)
            o[f"false_joins@{t}"] = sum(sum(r["sc"][n] >= t for n in r["neg"]) for r in rs) / len(rs)
        out[cond] = o
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--taus", default="0.5,0.6,0.7")
    ap.add_argument("--gate", type=float, default=None,
                    help="variant gate: skip variant comparisons for pairs scoring below this without hard evidence")
    ap.add_argument("--gold", default=gold_file(), help="gold labels (default: the local detailed file if present)")
    a = ap.parse_args()
    taus = [float(t) for t in a.taus.split(",")]
    profiles, gold = load_profiles(), json.load(open(a.gold, encoding="utf-8"))
    profiles = {k: v for k, v in profiles.items() if k in set(gold.get("case_ids") or profiles)}
    variants = load_variants(profiles)
    n_var = sum(len(v) for v in variants.values())
    print(f"cases: {len(profiles)}, cases with variants: {sorted(variants)}, variants: {n_var}")
    stats: Dict[str, int] = {}
    rows = run(profiles, variants, gold, taus, a.gate, stats)
    summ = summarize(rows, taus)
    if a.gate is not None:
        full = run(profiles, variants, gold, taus)["with"]
        lost = [(r["case"], p, round(f["sc"][p], 3), round(r["sc"][p], 3)) for r, f in zip(rows["with"], full)
                for p in r["sp"] if f["sc"][p] != r["sc"][p]]
        done, skipped = stats.get("variant_comparisons", 0), stats.get("variant_comparisons_skipped", 0)
        print(f"gate {a.gate}: variant comparisons done {done}, skipped {skipped}; "
              f"gold partner scores changed by the gate: {lost or 'none'}")
    keys = list(summ["without"])
    print(f"\n{'metric':<18}{'without':>10}{'with':>10}{'delta':>10}")
    for k in keys:
        w0, w1 = summ["without"][k], summ["with"][k]
        print(f"{k:<18}{w0:>10.3f}{w1:>10.3f}{w1 - w0:>+10.3f}")
    drift = [score(profiles[c], v)["score"] for c, vs in variants.items() for v in vs]
    if drift:
        print(f"\nvariant vs own parent: mean {sum(drift) / len(drift):.2f}, min {min(drift):.2f}, max {max(drift):.2f}"
              "  (low values = semantic drift)")
    demo = load_variants(profiles, "variants_demo.json")
    inv = [(c, score(profiles[c], v)["score"]) for c, vs in demo.items() for v in vs if v["_mutated_fields"] == [DEMO_SLOT]]
    if inv:
        print("demographics-only variants vs parent (must be 1.0):", [(c, round(s, 3)) for c, s in inv])
    else:
        print("demographics-invariance: no demographics-only variants yet (generate with --slots " + DEMO_SLOT + " --k 1 --tag _demo)")


if __name__ == "__main__":
    sys.exit(main())
