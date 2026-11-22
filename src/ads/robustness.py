"""Channel ablation and missing-data robustness, treating `similarity.score` as a black box.

    python -m ads.robustness channels   [--tau 0.55]            # switch each feature group off in turn
    python -m ads.robustness degrade    [--tau 0.55]            # test cases with material removed
    python -m ads.robustness make-degraded [--model M]          # LLM re-extraction of reduced inputs (uses quota)

Channel ablation masks a feature group in BOTH profiles of every pair, so any similarity implementation (the
placeholder or a replacement) can be evaluated without changes.

Degradation: the test case X loses material while the rest of the database stays complete; we ask whether X still
lands with its gold partners. Two kinds of scenario:
  * masked   (instant): drop the technical traces, or the templates, from X's profile;
  * real     (needs `make-degraded`): re-extract X from a reduced case input, either the ad creative only
             ("ad_only": no page, no logs) or the pages and logs only ("page_only": no ad creative). Real
             re-extraction is the honest test, because masking leaves information that came from the missing part.
"""
import argparse
import copy
import json
import os
import sys
from typing import Callable, Dict, List

from .clustering import pair_scores
from .evaluate import gold_pairs, load_profiles, require_profiles
from .paths import CASES, gold_file
from .similarity import score

STRICT = {"same_campaign", "same_template"}
BROAD = STRICT | {"same_scheme"}


def _infra(p):
    ta = p["technical_artifacts"]
    for k in ("urls_and_domains", "redirect_chain", "tracker_ids", "dom_and_form_clues", "domain_and_cert_metadata"):
        ta[k] = []
    ta["ad_library_metadata"]["page_id_or_name"] = None
    if ta.get("page_fingerprints"):
        ta["page_fingerprints"] = {**ta["page_fingerprints"], "images": []}


def _text(p):
    n = p["core_narrative"]
    n.update(narrative_pattern="", promise_and_mechanism="", call_to_action="", keywords=[])
    p["canonical_comparison_text"] = ""


def _templates(p):
    p["visual_and_production"].update(ad_creative_template=None, landing_page_template=None)
    ta = p["technical_artifacts"]
    if ta.get("page_fingerprints"):
        ta["page_fingerprints"] = {**ta["page_fingerprints"], "structure": []}


def _scam_topic(p):
    p["core_narrative"].update(ad_goal_scam_type="other", topic="other")


def _entities(p):
    e = p["entities"]
    e["product_or_platform"] = {"exact_name": None, "generic_category": None}
    e.update(featured_people=[], companies_or_institutions=[], impersonated_media=[])


def _persuasion(p):
    p["core_narrative"]["persuasion_devices"] = []


def _props_amounts(p):
    p["visual_and_production"]["setting_and_props"] = []
    p["entities"]["amounts_dates_locations"] = {"amounts": [], "dates": [], "locations": []}


GROUPS: Dict[str, Callable] = {
    "infrastructure (trackers, endpoints, domains, files, page images, sender page)": _infra,
    "text (summary, narrative, promise, CTA)": _text,
    "templates (ad + landing page, page structure)": _templates,
    "scam type + topic": _scam_topic,
    "entities (product, people, companies, media)": _entities,
    "persuasion devices": _persuasion,
    "props + amounts": _props_amounts,
}


def mask_profile(p: dict, groups: List[str]) -> dict:
    q = copy.deepcopy(p)
    for g in groups:
        GROUPS[g](q)
    return q


def _auc(pos: List[float], neg: List[float]) -> float:
    if not pos or not neg:
        return float("nan")
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def metrics(profiles: Dict[str, dict], gold: dict, tau: float) -> dict:
    ids = set(gold.get("case_ids") or profiles)
    profiles = {k: v for k, v in profiles.items() if k in ids}
    scores = pair_scores(profiles)
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    pos = [scores[p]["score"] for p in strict if p in scores]
    neg = [r["score"] for p, r in scores.items() if p not in broad]
    pred = {p for p, r in scores.items() if r["score"] >= tau}
    tp_b = len(pred & broad)
    triples = [t for t in gold["ranking_triples"] if {t["anchor"], t["closer"], t["farther"]} <= set(profiles)]
    sc = lambda a, b: scores[tuple(sorted((a, b)))]["score"]  # noqa: E731
    return {"auc": _auc(pos, neg), "pos": sum(pos) / len(pos), "neg": sum(neg) / len(neg),
            "triples": f"{sum(sc(t['anchor'], t['closer']) > sc(t['anchor'], t['farther']) for t in triples)}/{len(triples)}",
            "strict_recall": len(pred & strict) / len(strict) if strict else float("nan"),
            "broad_precision": tp_b / len(pred) if pred else 1.0, "broad_recall": tp_b / len(broad) if broad else float("nan")}


def channel_ablation(profiles, gold, tau):
    rows = [("all channels", metrics(profiles, gold, tau))]
    for g in GROUPS:
        rows.append((f"without {g}", metrics({k: mask_profile(v, [g]) for k, v in profiles.items()}, gold, tau)))
    return rows


# ---------------------------------------------------------------- degradation of one test case

def load_real_degraded(cid: str, scenario: str):
    f = os.path.join(CASES, cid, f"degraded_{scenario}.json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def degradation(profiles, gold, tau):
    ids = set(gold.get("case_ids") or profiles)
    profiles = {k: v for k, v in profiles.items() if k in ids}
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    partners = lambda x, pairs: {b if a == x else a for a, b in pairs if x in (a, b)}  # noqa: E731
    scenarios = {
        "full (baseline)": lambda x, p: p,
        "masked: no technical traces": lambda x, p: mask_profile(p, [list(GROUPS)[0]]),
        "masked: no templates": lambda x, p: mask_profile(p, [list(GROUPS)[2]]),
        "real: ad creative only": lambda x, p: load_real_degraded(x, "ad_only"),
        "real: pages + logs only": lambda x, p: load_real_degraded(x, "page_only"),
    }
    out = []
    for name, fn in scenarios.items():
        n = rec = top1 = fj = 0
        means = []
        for x in sorted(profiles):
            sp, bp = partners(x, strict), partners(x, broad)
            deg = fn(x, profiles[x])
            if not sp or deg is None:
                continue
            others = [y for y in profiles if y != x]
            s = {y: score(deg, profiles[y])["score"] for y in others}
            n += 1
            means.append(sum(s[y] for y in sp) / len(sp))
            rec += sum(s[y] >= tau for y in sp) / len(sp)
            fj += sum(s[y] >= tau for y in others if y not in bp)
            top1 += max(s, key=s.get) in bp
        out.append((name, {"cases": n, "mean_partner_score": sum(means) / n if n else float("nan"),
                           "partner_recall": rec / n if n else float("nan"),
                           "false_joins_per_case": fj / n if n else float("nan"),
                           "top1_is_partner": top1 / n if n else float("nan")}))
    return out


def make_degraded(model: str, cases: List[str] = None) -> None:
    """Re-extract reduced inputs through the LLM (one call per case and scenario)."""
    from .llm.client import make_client
    from .llm.extract import extract
    cases_dir = CASES
    client = make_client(extraction_model=model)
    for cid in cases or sorted(os.listdir(cases_dir)):
        f = os.path.join(cases_dir, cid, "case_input.json")
        if not os.path.exists(f):
            continue
        case = json.load(open(f, encoding="utf-8"))
        roles = {p["role"] for p in case["parts"]}
        if "ad_creative" not in roles or roles == {"ad_creative"}:
            continue  # needs both an ad and at least one page to make two different reduced inputs
        no_tech = {k: [] for k in case["technical_summary"]}
        for scenario, parts, tech in (
                ("ad_only", [p for p in case["parts"] if p["role"] == "ad_creative"], no_tech),
                ("page_only", [p for p in case["parts"] if p["role"] != "ad_creative"], case["technical_summary"])):
            out = os.path.join(cases_dir, cid, f"degraded_{scenario}.json")
            if os.path.exists(out):
                continue
            reduced = dict(case, parts=copy.deepcopy(parts), technical_summary=tech)
            try:
                prof = extract(reduced, client)
            except Exception as e:  # noqa: BLE001
                print(f"case {cid} {scenario}: FAILED {str(e)[:120]}")
                continue
            json.dump(prof, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"case {cid} {scenario}: ok ({prof['core_narrative']['ad_goal_scam_type']})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["channels", "degrade", "make-degraded"])
    ap.add_argument("--tau", type=float, default=0.55)
    ap.add_argument("--model", default="gemini-3.5-flash-lite")
    ap.add_argument("--gold", default=gold_file(), help="gold labels (default: the local detailed file if present)")
    a = ap.parse_args()
    if a.cmd == "make-degraded":
        return make_degraded(a.model)
    profiles, gold = require_profiles(load_profiles()), json.load(open(a.gold, encoding="utf-8"))
    if a.cmd == "channels":
        print(f"channel ablation at tau={a.tau} (cases: {len(profiles)})\n")
        print(f"{'condition':<72}{'AUC':>6}{'pos':>6}{'neg':>6}{'trip':>6}{'strRec':>7}{'brdP':>6}{'brdR':>6}")
        for name, m in channel_ablation(profiles, gold, a.tau):
            print(f"{name:<72}{m['auc']:>6.2f}{m['pos']:>6.2f}{m['neg']:>6.2f}{m['triples']:>6}{m['strict_recall']:>7.2f}"
                  f"{m['broad_precision']:>6.2f}{m['broad_recall']:>6.2f}")
    else:
        print(f"missing-data robustness at tau={a.tau}: test case degraded, rest of the database complete\n")
        print(f"{'scenario':<34}{'cases':>6}{'partner score':>15}{'partner recall':>16}{'false joins/case':>18}{'top1 is partner':>17}")
        for name, m in degradation(profiles, gold, a.tau):
            print(f"{name:<34}{m['cases']:>6}{m['mean_partner_score']:>15.2f}{m['partner_recall']:>16.2f}"
                  f"{m['false_joins_per_case']:>18.2f}{m['top1_is_partner']:>17.2f}")


if __name__ == "__main__":
    sys.exit(main())
