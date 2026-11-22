"""Similarity and grouping against the gold labels.

    python -m ads.evaluation.evaluate [--tau 0.6] [--gold FILE] [--matrix] [--variants]

Reports the ranking constraints (similarity(anchor, closer) > similarity(anchor, farther)), the mean score of
same-campaign and unrelated pairs, and pairwise precision / recall / F1 on two levels: campaigns against the strict
gold, families of campaigns against the broad gold. --variants adds the synthetic variants as extra comparisons.
"""
import argparse
import os
from typing import Dict, Optional

from ..clustering import FAMILY_SCORE, TAU, cluster, hierarchy, load_variants, pair_scores
from ..database import load_profiles, require_profiles
from ..paths import gold_file
from .gold import BROAD, STRICT, gold_pairs, group_pairs, labelled, load_gold, mean, prf, ranking


def evaluate(profiles: Dict[str, dict], gold: dict, tau: float, scores: Optional[dict] = None) -> dict:
    profiles = labelled(profiles, gold)
    scores = {k: v for k, v in (scores or pair_scores(profiles)).items() if k[0] in profiles and k[1] in profiles}
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    groups = cluster(profiles, tau, scores)
    families = [sorted(c for i in f for c in groups[i]) for f in hierarchy(profiles, groups, FAMILY_SCORE, scores)]
    pos = [scores[p]["score"] for p in strict if p in scores]
    neg = [r["score"] for p, r in scores.items() if p not in broad]
    return {"triples": [(t, c, f, c > f) for t, c, f in ranking(gold, scores, profiles)],
            "mean_strict_positive": mean(pos), "mean_negative": mean(neg),
            "groups": groups, "families": families,
            "strict": prf(group_pairs(groups), strict), "broad": prf(group_pairs(groups), broad),
            "family_broad": prf(group_pairs(families), broad)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tau", type=float, default=TAU)
    ap.add_argument("--gold", default=gold_file(), help="gold labels (default: the local detailed file if present)")
    ap.add_argument("--matrix", action="store_true", help="also print the score of every pair")
    ap.add_argument("--variants", action="store_true", help="synthetic variants as extra comparisons (never grouped)")
    a = ap.parse_args()
    profiles, gold = require_profiles(load_profiles()), load_gold(a.gold)
    variants = load_variants(profiles) if a.variants else None
    scores = pair_scores(profiles, variants)
    r = evaluate(profiles, gold, a.tau, scores)
    if variants:
        print(f"variants: {sum(len(v) for v in variants.values())} for {len(variants)} cases")
    print(f"cases: {len(profiles)}  gold: {os.path.basename(a.gold)}  tau: {a.tau}")
    print(f"ranking triples: {sum(t[3] for t in r['triples'])}/{len(r['triples'])} correct")
    for t, c, f, ok in r["triples"]:
        print(f"  {'ok ' if ok else 'BAD'} sim({t['anchor']},{t['closer']})={c:.2f} vs sim({t['anchor']},{t['farther']})={f:.2f}")
    print(f"mean score: strict-positive pairs {r['mean_strict_positive']:.2f}, unrelated pairs {r['mean_negative']:.2f}")
    print("campaigns vs strict gold P/R/F1 %.2f/%.2f/%.2f (vs broad %.2f/%.2f/%.2f)" % (*r["strict"], *r["broad"]))
    print("families  vs broad gold  P/R/F1 %.2f/%.2f/%.2f" % r["family_broad"])
    print("campaigns:", [g for g in r["groups"] if len(g) > 1], "| single:", [g[0] for g in r["groups"] if len(g) == 1])
    print("families:", [f for f in r["families"] if len(f) > 1])
    if a.matrix:
        ids = sorted(profiles)
        print("\n     " + "".join(f"{i:>6}" for i in ids))
        for i in ids:
            print(f"{i:>4} " + "".join("   -  " if i == j else f"{scores[tuple(sorted((i, j)))]['score']:6.2f}" for j in ids))


if __name__ == "__main__":
    main()
