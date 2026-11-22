"""python -m ads.explain A B [--tau 0.6]   or   python -m ads.explain --campaigns"""
import argparse
import sys
from typing import Any, Dict

from ..analysis import campaigns, pair_table
from ..database import load_profiles, require_profiles
from .campaign import campaign
from .pair import pair


def format_pair(ex: Dict[str, Any], ida: str, idb: str) -> str:
    lines = [f"{ida} <-> {idb}: score {ex['score']:.2f}" + ("  (hard evidence: joined whatever the score)"
                                                             if ex["must_link"] else "")]
    lines += [f"  evidence  {e['text']}" + ("  [must-link]" if e["must_link"] else "") for e in ex["evidence"]]
    lines.append("  by group                         share   similarity   score without it")
    for g in ex["groups"]:
        wo = "n/a" if g["without"] is None else f"{g['without']:.2f}"
        lines.append(f"    {g['group']:<28} {g['contribution']:>6.2f}   {g['similarity']:>9.2f}   {wo:>8}"
                     + ("  <- crosses tau" if g.get("crosses_tau") else ""))
    lines.append("  features (contribution, similarity, shared values)")
    for f in ex["features"]:
        v = f["values"]
        if f["contribution"] is None:
            if f["missing"]:
                lines.append(f"    {f['feature']:<24} not comparable (no data: {f['missing']})")
            continue
        shared = ", ".join(v["shared_words"][:8]) if "shared_words" in v else \
            ", ".join(m["a"] if m["a"] == m["b"] else f"{m['a']} ~ {m['b']}" for m in v["shared"]) if "shared" in v else \
            f"{v.get('a')} | {v.get('b')}"
        lines.append(f"    {f['feature']:<24} {f['contribution']:>5.2f} {f['similarity']:>5.2f}  {shared[:90]}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Explain why cases are linked")
    ap.add_argument("cases", nargs="*", help="two case ids")
    ap.add_argument("--tau", type=float, default=0.6)
    ap.add_argument("--campaigns", action="store_true", help="explain every campaign at tau")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    profiles = require_profiles(load_profiles())
    if not a.campaigns:
        if len(a.cases) != 2 or any(c not in profiles for c in a.cases):
            sys.exit(f"give two case ids from: {', '.join(sorted(profiles))}")
        print(format_pair(pair(profiles[a.cases[0]], profiles[a.cases[1]], a.tau), *a.cases))
        return
    scores, groups = pair_table(profiles), campaigns(profiles, a.tau)
    for i, g in enumerate(groups, 1):
        ex = campaign(g, profiles, scores, a.tau, groups)
        cohesion = f"  cohesion min {ex['cohesion']['min']:.2f} mean {ex['cohesion']['mean']:.2f}" if ex["cohesion"] else ""
        print(f"K{i}: {', '.join(g)}  rule: {ex['rule']} [{' | '.join(','.join(p) for p in ex['parts'])}]{cohesion}")
        for s in ex["signature"]:
            print(f"    shared {s['feature']}: {s['value']} ({s['count']}/{s['of']})")
        n = ex.get("nearest")
        if n:
            print(f"    nearest other: {', '.join(n['members'])} mean {n['mean']:.2f} (tau {a.tau}), "
                  f"best pair {n['best_pair']['a']}-{n['best_pair']['b']} {n['best_pair']['score']:.2f}")


if __name__ == "__main__":
    main()
