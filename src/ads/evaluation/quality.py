"""Grouping quality measured the way the organiser will test it (task, section 6): new material is analysed against
the database exactly as in the panel (analysis.compare) and its outcome is checked against the gold labels.

    python -m ads.evaluation.quality [--tau 0.6] [--json]
    python -m ads.evaluation.quality --sweep    # the same tests for tau 0.30 .. 0.80

Three tests, each item ending as correct, missed (a known campaign was not joined) or false join (joined a campaign
it has no gold relation to):
  leave-one-out   each real case is removed from the database and analysed as new material. Expected: it joins a
                  campaign holding one of its strict gold partners, or stays new when it has none.
  variants        the synthetic variants (data/cases/<id>/variants*.json: same scam blueprint, swapped surface
                  details) as new versions of known campaigns. Two settings: parent known (the parent is in the
                  database: it must join the parent's campaign) and parent held out (the parent is removed: it must join
                  a campaign of the parent's strict partners, or stay new). Each with the parent's technical traces
                  (same operator) and without them (new infrastructure: content alone must carry the link).
  must-not-link   every item above that should stay new: the share that was wrongly joined to a campaign.
Both levels are judged: campaigns (purity: joined cases that are the same campaign in gold) and families of campaigns
(against the broad gold). Variants are only ever compared with real cases, never with each other.
"""
import argparse
import copy
import json
from collections import Counter
from typing import Dict, List, Optional, Set

from ..analysis import compare
from ..clustering import FAMILY_SCORE, TAU, load_variants
from ..database import load_profiles, require_profiles
from ..schema import empty_tech
from .gold import BROAD, STRICT, gold_pairs, labelled, load_gold, mean, partners

LOO = "leave-one-out (real cases)"
# the variant tests: (name, short name in --sweep, parent in the database, parent's technical traces kept)
VARIANT_TESTS = [(f"variants, parent {'known' if known else 'held out'}, {'same' if infra else 'new'} infrastructure",
                  f"{'known' if known else 'held'}+{'same' if infra else 'new'}", known, infra)
                 for known in (True, False) for infra in (True, False)]
SHORT = {LOO: "LOO", **{name: short for name, short, _, _ in VARIANT_TESTS}}
MUST_NOT_LINK = "must-not-link (all items that should stay new)"


def strip_infrastructure(p: dict) -> dict:
    """The profile as if the same content had been published on new infrastructure (no traces in common)."""
    q = copy.deepcopy(p)
    q["technical_artifacts"] = {**empty_tech(), "ad_library_metadata": {}}
    return q


def _kind(joined: Set[str], expected: Set[str], related: Set[str]) -> str:
    if joined - related:
        return "false join"          # grouped with a case it has no gold relation to
    if expected:
        return "correct" if joined & expected else "missed"
    return "correct"                 # nothing known to join: stayed new (or joined only related cases)


def outcome(profile: dict, db: Dict[str, dict], tau: float, expected: Set[str], related: Set[str]) -> Dict[str, object]:
    """Analyse `profile` against `db` and classify the result. `expected`: cases it should be grouped with (strict
    gold, in db); `related`: cases it may be grouped with without counting as a false join (broad gold)."""
    res = compare(profile, None, db, tau, fingerprints={})
    joined = {c for g in res["joins"] for c in g}
    family = {c for f in res["family_joins"] for c in f}
    return {"outcome": _kind(joined, expected, related), "family_outcome": _kind(family, related, related),
            "purity": len(joined & expected) / len(joined) if joined else None,  # same scheme counts as wrong here
            "status": res["decision"]["status"], "joined": sorted(joined), "expected": sorted(expected)}


def _share(rows: List[dict], kind: str) -> float:
    return sum(r["outcome"] == kind for r in rows) / len(rows) if rows else float("nan")


def summarise(rows: List[dict]) -> Dict[str, object]:
    n = len(rows) or 1
    count = Counter(r["outcome"] for r in rows)
    should_join = [r for r in rows if r["expected"]]
    should_stay = [r for r in rows if not r["expected"]]
    return {
        "n": len(rows), "accuracy": count["correct"] / n, "false_join_rate": count["false join"] / n,
        "join_recall": _share(should_join, "correct"), "stay_new_correct": _share(should_stay, "correct"),
        "family_accuracy": sum(r["family_outcome"] == "correct" for r in rows) / n,
        "family_false_join_rate": sum(r["family_outcome"] == "false join" for r in rows) / n,
        "purity": mean([r["purity"] for r in rows if r["purity"] is not None]),
        "n_should_join": len(should_join), "n_should_stay": len(should_stay),
        "statuses": dict(Counter(r["status"] for r in rows)),
    }


def leave_one_out(profiles: Dict[str, dict], gold: dict, tau: float) -> List[dict]:
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    rows = []
    for cid in sorted(profiles):
        db = {k: v for k, v in profiles.items() if k != cid}
        rows.append({"item": cid, **outcome(profiles[cid], db, tau, partners(cid, strict) & set(db),
                                            partners(cid, broad) & set(db))})
    return rows


def variant_test(profiles: Dict[str, dict], variants: Dict[str, List[dict]], gold: dict, tau: float,
                 parent_known: bool, with_infrastructure: bool) -> List[dict]:
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    rows = []
    for parent, vs in sorted(variants.items()):
        db = dict(profiles) if parent_known else {k: v for k, v in profiles.items() if k != parent}
        expected = (partners(parent, strict) | ({parent} if parent_known else set())) & set(db)
        related = expected | (partners(parent, broad) & set(db))
        for i, v in enumerate(vs):
            v = {k: x for k, x in v.items() if not k.startswith("_")}
            if not with_infrastructure:
                v = strip_infrastructure(v)
            rows.append({"item": f"{parent}:v{i}", **outcome(v, db, tau, expected, related)})
    return rows


def run(tau: float, profiles: Optional[Dict[str, dict]] = None, gold: Optional[dict] = None,
        variants: Optional[Dict[str, List[dict]]] = None) -> Dict[str, Dict[str, object]]:
    gold = gold if gold is not None else load_gold()
    profiles = labelled(profiles if profiles is not None else require_profiles(load_profiles()), gold)
    variants = variants if variants is not None else load_variants(profiles)
    report = {LOO: summarise(leave_one_out(profiles, gold, tau))}
    if variants:
        for name, _, known, infra in VARIANT_TESTS:
            report[name] = summarise(variant_test(profiles, variants, gold, tau, known, infra))
    stay = [r for r in report.values() if r["n_should_stay"]]
    n_stay = sum(r["n_should_stay"] for r in stay)
    report[MUST_NOT_LINK] = {"n": n_stay, "stay_new_correct":
                             sum(r["stay_new_correct"] * r["n_should_stay"] for r in stay) / max(1, n_stay)}
    return report


def sweep(taus, profiles=None, gold=None, variants=None) -> List[Dict[str, object]]:
    """run() for every tau: per test the share of correct outcomes and of false joins."""
    profiles = profiles if profiles is not None else require_profiles(load_profiles())
    variants = variants if variants is not None else load_variants(profiles)
    rows = []
    for tau in taus:
        rep = run(round(tau, 2), profiles, gold, variants)
        tests = {SHORT[k]: r for k, r in rep.items() if k in SHORT}
        rows.append({"tau": round(tau, 2), "tests": {k: (r["accuracy"], r["false_join_rate"]) for k, r in tests.items()},
                     "purity": {k: r["purity"] for k, r in tests.items()},
                     "stay_new": rep[MUST_NOT_LINK]["stay_new_correct"]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Grouping quality on new material: leave-one-out, variants, must-not-link")
    ap.add_argument("--tau", type=float, default=TAU)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--sweep", action="store_true", help="the tests for tau 0.30 .. 0.80 (correct / false joins)")
    a = ap.parse_args()
    if a.sweep:
        rows = sweep([0.30 + 0.05 * i for i in range(11)])
        names = list(rows[0]["tests"])
        print("correct / false joins per test and tau (stay new = items without a known campaign left new; "
              "purity = joined cases that are the same campaign in gold, per test)\n")
        print(f"{'tau':>5}  " + "".join(f"{n:>13}" for n in names) + f"{'stay new':>10}")
        for r in rows:
            print(f"{r['tau']:>5.2f}  " + "".join(f"{r['tests'][n][0]:>7.2f}/{r['tests'][n][1]:<5.2f}" for n in names)
                  + f"{r['stay_new']:>10.2f}   purity " + " ".join(f"{r['purity'][n]:.2f}" for n in names))
        return
    report = run(a.tau)
    if a.json:
        print(json.dumps(report, indent=2))
        return
    print(f"grouping quality on new material at tau={a.tau}\n")
    print(f"{'':<58}{'':>5}{'--------- campaigns ---------':>37}{'-- families --':>24}")
    print(f"{'test':<58}{'n':>5}{'acc':>7}{'join rec':>10}{'false join':>12}{'purity':>8}{'stay new':>10}"
          f"{'acc':>8}{'false join':>12}")
    for name, r in report.items():
        if "accuracy" not in r:
            print(f"{name:<58}{r['n']:>5}{'':>7}{'':>10}{'':>12}{r['stay_new_correct']:>10.2f}")
            continue
        print(f"{name:<58}{r['n']:>5}{r['accuracy']:>7.2f}{r['join_recall']:>10.2f}{r['false_join_rate']:>12.2f}"
              f"{r['purity']:>8.2f}{r['stay_new_correct']:>10.2f}{r['family_accuracy']:>8.2f}"
              f"{r['family_false_join_rate']:>12.2f}")
    print("\nacc = correct outcome; join rec = share of items with a known campaign that joined it; false join = joined a "
          "campaign with no gold relation (same scheme counts as related); purity = share of the joined cases that are the "
          "same campaign or template in gold (same scheme counts as wrong here); stay new = items without a known "
          f"campaign left as new. families: the same at the second level (same scam type and score >= {FAMILY_SCORE:.2f} "
          "or family evidence: shared tool, page kit or tracking template), judged against the broad gold.")


if __name__ == "__main__":
    main()
