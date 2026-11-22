"""Does adding the synthetic variants to the database help grouping?

    python -m ads.evaluation.ablation [--taus 0.5,0.6,0.7]

Leave one case out: case X is scored against the originals of all other cases, and in the "with" condition also
against their variants (never X's own). Averaged over cases with gold partners: partner recall and false joins at
each tau, and P(score(X, partner) > score(X, non-partner)). Also: how close each variant stays to its parent, and
that a variant changing only demographics of unidentified people scores exactly 1.0 (CLAUDE.md rule 5).
"""
import argparse

from ..clustering import best_score, load_variants
from ..database import load_profiles, require_profiles
from ..similarity import score
from .gold import BROAD, STRICT, gold_pairs, labelled, load_gold, partners

DEMO_SLOT = "non_grouping_attributes.unidentified_people_demographics"


def run(profiles, variants, gold):
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    rows = {"without": [], "with": []}
    for x in profiles:
        sp, bp = partners(x, strict) & set(profiles), partners(x, broad) & set(profiles)
        if not sp:
            continue
        others = [y for y in profiles if y != x]
        neg = [y for y in others if y not in bp]
        for cond, sc in (("without", {y: score(profiles[x], profiles[y])["score"] for y in others}),
                         ("with", {y: best_score(profiles[x], profiles[y], None, variants.get(y))["score"]
                                   for y in others})):
            wins = [sc[p] > sc[n] for p in sp for n in neg]
            rows[cond].append({"sc": sc, "sp": sp, "neg": neg, "rank_acc": sum(wins) / len(wins) if wins else None})
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
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--taus", default="0.5,0.6,0.7")
    a = ap.parse_args()
    taus = [float(t) for t in a.taus.split(",")]
    gold = load_gold()
    profiles = labelled(require_profiles(load_profiles()), gold)
    variants = load_variants(profiles)
    print(f"cases: {len(profiles)}, variants: {sum(len(v) for v in variants.values())} of {len(variants)} cases")
    summ = summarize(run(profiles, variants, gold), taus)
    print(f"\n{'metric':<18}{'without':>10}{'with':>10}{'delta':>10}")
    for k in summ["without"]:
        w0, w1 = summ["without"][k], summ["with"][k]
        print(f"{k:<18}{w0:>10.3f}{w1:>10.3f}{w1 - w0:>+10.3f}")
    drift = [score(profiles[c], v)["score"] for c, vs in variants.items() for v in vs]
    if drift:
        print(f"\nvariant vs own parent: mean {sum(drift) / len(drift):.2f}, min {min(drift):.2f}, max {max(drift):.2f}")
    demo = [(c, score(profiles[c], v)["score"]) for c, vs in variants.items() for v in vs
            if v.get("_mutated_fields") == [DEMO_SLOT]]
    print("demographics-only variants vs parent (must be 1.0):", [(c, round(s, 3)) for c, s in demo] or "none generated")


if __name__ == "__main__":
    main()
