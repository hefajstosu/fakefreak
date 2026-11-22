"""Grouping quality measured the way the organiser will test it (task, section 6): new material is analysed against
the database exactly as in the panel (analyze.compare) and its outcome is checked against the gold labels.

    python -m ads.quality [--tau 0.6]

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
Variants are synthetic and only ever compared with real cases (never with each other), as in clustering.
"""
import argparse
import copy
import json
import sys
from collections import Counter
from typing import Dict, List, Optional, Set

from . import analyze as an
from .clustering import load_all_variants
from .evaluate import gold_pairs, load_profiles, require_profiles
from .paths import gold_file
from .robustness import BROAD, STRICT

OUTCOMES = ("correct", "missed", "false join")


def partners(cid: str, pairs: Set[tuple]) -> Set[str]:
    return {b if a == cid else a for a, b in pairs if cid in (a, b)}


def strip_infrastructure(p: dict) -> dict:
    """The profile as if the same content had been published on new infrastructure (no traces in common)."""
    q = copy.deepcopy(p)
    q["technical_artifacts"] = {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [], "dom_and_form_clues": [],
                                "domain_and_cert_metadata": [], "ad_library_metadata": {}}
    return q


def outcome(profile: dict, db: Dict[str, dict], tau: float, expected: Set[str], related: Set[str]) -> Dict[str, object]:
    """Analyse `profile` against `db` and classify the result. `expected`: cases it should be grouped with (strict
    gold, in db); `related`: cases it may be grouped with without counting as a false join (broad gold)."""
    res = an.compare(profile, None, db, tau, fingerprints={})
    joined = {c for g in res["joins"] for c in g}
    if joined - related:
        kind = "false join"          # grouped with a case it has no gold relation to
    elif expected:
        kind = "correct" if joined & expected else "missed"
    else:
        kind = "correct"             # nothing known to join: stayed new (or joined only broadly related cases)
    return {"outcome": kind, "status": res["decision"]["status"], "joined": sorted(joined), "expected": sorted(expected)}


def summarise(rows: List[dict]) -> Dict[str, object]:
    n = len(rows)
    count = Counter(r["outcome"] for r in rows)
    should_join = [r for r in rows if r["expected"]]
    should_stay = [r for r in rows if not r["expected"]]
    return {
        "n": n, "accuracy": count["correct"] / n if n else float("nan"),
        "join_recall": sum(r["outcome"] == "correct" for r in should_join) / len(should_join) if should_join else float("nan"),
        "false_join_rate": count["false join"] / n if n else float("nan"),
        "stay_new_correct": sum(r["outcome"] == "correct" for r in should_stay) / len(should_stay) if should_stay else float("nan"),
        "n_should_join": len(should_join), "n_should_stay": len(should_stay), "outcomes": dict(count),
        "statuses": dict(Counter(r["status"] for r in rows)),
    }


def leave_one_out(profiles: Dict[str, dict], gold: dict, tau: float) -> List[dict]:
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    rows = []
    for cid in sorted(profiles):
        db = {k: v for k, v in profiles.items() if k != cid}
        rows.append({"item": cid, **outcome(profiles[cid], db, tau, partners(cid, strict) & set(db),
                                            (partners(cid, broad) | partners(cid, strict)) & set(db))})
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
    profiles = profiles if profiles is not None else require_profiles(load_profiles())
    gold = gold if gold is not None else json.load(open(gold_file(), encoding="utf-8"))
    ids = set(gold.get("case_ids") or profiles)
    profiles = {k: v for k, v in profiles.items() if k in ids}
    variants = variants if variants is not None else load_all_variants(profiles)
    report = {"leave-one-out (real cases)": summarise(leave_one_out(profiles, gold, tau))}
    if variants:
        for known in (True, False):
            for infra in (True, False):
                name = (f"variants, parent {'known' if known else 'held out'}, "
                        f"{'same infrastructure' if infra else 'new infrastructure'}")
                report[name] = summarise(variant_test(profiles, variants, gold, tau, known, infra))
    stay = [r for r in report.values() if r["n_should_stay"]]
    report["must-not-link (all items that should stay new)"] = {
        "n": sum(r["n_should_stay"] for r in stay),
        "stay_new_correct": (sum(r["stay_new_correct"] * r["n_should_stay"] for r in stay) /
                             max(1, sum(r["n_should_stay"] for r in stay))),
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Grouping quality on new material: leave-one-out, variants, must-not-link")
    ap.add_argument("--tau", type=float, default=0.6)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args()
    report = run(a.tau)
    if a.json:
        print(json.dumps(report, indent=2))
        return
    print(f"grouping quality on new material at tau={a.tau}\n")
    print(f"{'test':<58}{'n':>5}{'acc':>7}{'join rec':>10}{'false join':>12}{'stay new':>10}")
    for name, r in report.items():
        if "accuracy" not in r:
            print(f"{name:<58}{r['n']:>5}{'':>7}{'':>10}{'':>12}{r['stay_new_correct']:>10.2f}")
            continue
        print(f"{name:<58}{r['n']:>5}{r['accuracy']:>7.2f}{r['join_recall']:>10.2f}{r['false_join_rate']:>12.2f}"
              f"{r['stay_new_correct']:>10.2f}")
    print("\nacc = correct outcome; join rec = share of items with a known campaign that joined it; false join = joined a "
          "campaign with no gold relation; stay new = items without a known campaign left as new.")


if __name__ == "__main__":
    main()
