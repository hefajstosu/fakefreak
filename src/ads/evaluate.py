"""Evaluate the similarity + clustering against the gold labels.

    python -m ads.evaluate [--tau 0.6] [--gold data/gold/groups.local.json] [--matrix]

Reports: ranking-triple accuracy (similarity(anchor, closer) > similarity(anchor, farther)),
separation of strict positive pairs from negatives, and pairwise precision/recall/F1 of the
clusters against the strict gold (same_campaign + same_template) and broad gold (+ same_scheme).
"""
import argparse
import glob
import json
import os
import sys
from itertools import combinations
from typing import Dict, Set

from .clustering import cluster, load_variants, pair_scores

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def case_meta(cid: str, cases_dir: str = None) -> dict:
    """Optional data/cases/<id>/meta.json written by the demo: {"status": "unconfirmed"|"confirmed", "duplicate_of": id}."""
    f = os.path.join(cases_dir or os.path.join(REPO, "data", "cases"), cid, "meta.json")
    try:
        return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    except ValueError:
        return {}


def load_profiles(cases_dir: str = None) -> Dict[str, dict]:
    cases_dir = cases_dir or os.path.join(REPO, "data", "cases")
    out = {}
    for f in glob.glob(os.path.join(cases_dir, "*", "profile.json")):
        cid = os.path.basename(os.path.dirname(f))
        if case_meta(cid, cases_dir).get("duplicate_of"):
            continue  # duplicates are attached to their original, not counted as separate cases
        out[cid] = json.load(open(f, encoding="utf-8"))
    return out


def gold_pairs(gold: dict, levels: Set[str]) -> Set[tuple]:
    pairs = set()
    for g in gold["groups"]:
        if g["level"] in levels:
            pairs |= {tuple(sorted(p)) for p in combinations(g["members"], 2)}
    return pairs


def prf(pred: Set[tuple], truth: Set[tuple]):
    tp = len(pred & truth)
    p = tp / len(pred) if pred else 1.0
    r = tp / len(truth) if truth else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def evaluate(profiles: Dict[str, dict], gold: dict, tau: float, scores=None, variants=None, variant_gate=None) -> dict:
    ids = set(gold.get("case_ids") or profiles)  # cases saved from the demo are not in the gold labels
    profiles = {k: v for k, v in profiles.items() if k in ids}
    scores = {k: v for k, v in (scores or pair_scores(profiles, variants, variant_gate)).items() if k[0] in ids and k[1] in ids}
    sc = lambda a, b: scores[tuple(sorted((a, b)))]["score"]  # noqa: E731
    triples = [t for t in gold["ranking_triples"] if {t["anchor"], t["closer"], t["farther"]} <= set(profiles)]
    ok = [(t, sc(t["anchor"], t["closer"]), sc(t["anchor"], t["farther"])) for t in triples]
    strict, broad = gold_pairs(gold, {"same_campaign", "same_template"}), gold_pairs(gold, {"same_campaign", "same_template", "same_scheme"})
    groups = cluster(profiles, tau, scores)
    pred = {tuple(sorted(p)) for g in groups for p in combinations(g, 2)}
    pos = [scores[p]["score"] for p in strict if p in scores]
    neg = [r["score"] for p, r in scores.items() if p not in broad]
    return {
        "triples": [(t, c, f, c > f) for t, c, f in ok],
        "triple_accuracy": sum(c > f for _, c, f in ok) / len(ok) if ok else None,
        "mean_strict_positive": sum(pos) / len(pos) if pos else None,
        "mean_negative": sum(neg) / len(neg) if neg else None,
        "strict": prf(pred, strict), "broad": prf(pred, broad), "groups": groups,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau", type=float, default=0.6)
    ap.add_argument("--gold", default=os.path.join(REPO, "data", "gold", "groups.local.json"))
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--variants", action="store_true",
                    help="use the synthetic variants (data/cases/*/variants.json) as extra comparisons; they are never grouped")
    ap.add_argument("--gate", type=float, default=None, help="variant gate (see clustering/pairs.py); needs --variants")
    a = ap.parse_args()
    if not os.path.exists(a.gold):
        a.gold = os.path.join(REPO, "data", "gold", "groups.json")
    profiles, gold = load_profiles(), json.load(open(a.gold, encoding="utf-8"))
    variants = load_variants(profiles) if a.variants else None
    stats = {}
    scores = pair_scores(profiles, variants, a.gate, stats)
    r = evaluate(profiles, gold, a.tau, scores)
    if a.variants:
        print(f"variants: {sum(len(v) for v in variants.values())} for {len(variants)} cases; comparisons {stats}")
    print(f"cases: {len(profiles)}  gold: {os.path.basename(a.gold)}  tau: {a.tau}")
    print(f"ranking triples: {sum(t[3] for t in r['triples'])}/{len(r['triples'])} correct")
    for t, c, f, ok in r["triples"]:
        print(f"  {'ok ' if ok else 'BAD'} sim({t['anchor']},{t['closer']})={c:.2f} vs sim({t['anchor']},{t['farther']})={f:.2f}")
    print(f"mean score: strict-positive pairs {r['mean_strict_positive']:.2f}, unrelated pairs {r['mean_negative']:.2f}")
    print("pairwise P/R/F1  strict: %.2f/%.2f/%.2f   broad: %.2f/%.2f/%.2f" % (*r["strict"], *r["broad"]))
    print("clusters:", [g for g in r["groups"] if len(g) > 1], "| singletons:", [g[0] for g in r["groups"] if len(g) == 1])
    if a.matrix:
        ids = sorted(profiles)
        print("\n     " + "".join(f"{i:>6}" for i in ids))
        for i in ids:
            print(f"{i:>4} " + "".join("   -  " if i == j else f"{scores[tuple(sorted((i, j)))]['score']:6.2f}" for j in ids))


if __name__ == "__main__":
    sys.exit(main())
