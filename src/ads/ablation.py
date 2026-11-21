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
import glob
import json
import os
import sys
from typing import Dict, List

from .evaluate import REPO, gold_pairs, load_profiles
from .llm.generate import profile_sha, variant_to_profile
from .similarity import score

DEMO_SLOT = "non_grouping_attributes.unidentified_people_demographics"


def load_variants(profiles: Dict[str, dict], name: str = "variants.json") -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for cid, parent in profiles.items():
        f = os.path.join(REPO, "data", "cases", cid, name)
        if os.path.exists(f):
            data = json.load(open(f, encoding="utf-8"))
            if data.get("parent_profile_sha") not in (None, profile_sha(cid)):
                print(f"warning: variants of case {cid} are stale (profile changed since generation), skipped: {name}")
                continue
            parent = dict(parent, _case_id=cid)
            out[cid] = [variant_to_profile(parent, v) for v in data["variants"]]
    return out


def partners(gold: dict, cid: str, levels) -> set:
    return {b if a == cid else a for a, b in gold_pairs(gold, levels) if cid in (a, b)}


def run(profiles, variants, gold, taus):
    strict_lv, broad_lv = {"same_campaign", "same_template"}, {"same_campaign", "same_template", "same_scheme"}
    rows = {"without": [], "with": []}
    for x in profiles:
        sp, bp = partners(gold, x, strict_lv) & set(profiles), partners(gold, x, broad_lv) & set(profiles)
        if not sp:
            continue
        others = [y for y in profiles if y != x]
        s_wo = {y: score(profiles[x], profiles[y])["score"] for y in others}
        s_w = {y: max([s_wo[y]] + [score(profiles[x], v)["score"] for v in variants.get(y, [])]) for y in others}
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
    ap.add_argument("--gold", default=os.path.join(REPO, "data", "gold", "groups.local.json"))
    a = ap.parse_args()
    if not os.path.exists(a.gold):
        a.gold = os.path.join(REPO, "data", "gold", "groups.json")
    taus = [float(t) for t in a.taus.split(",")]
    profiles, gold = load_profiles(), json.load(open(a.gold, encoding="utf-8"))
    variants = load_variants(profiles)
    n_var = sum(len(v) for v in variants.values())
    print(f"cases: {len(profiles)}, cases with variants: {sorted(variants)}, variants: {n_var}")
    summ = summarize(run(profiles, variants, gold, taus), taus)
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
