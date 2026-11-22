"""Why two cases are linked, why a campaign holds together, why a new article joined a campaign or did not.

Reporting only: nothing here changes a score, a group or a decision. Every number is recomputed with the same
functions, weights and anchor settings as `similarity.score()`, so a pair explanation always adds up to the score.

    pair(a, b)                                   per-feature breakdown that sums to the score, the values both cases
                                                 share, the values that differ, what could not be compared, the hard
                                                 evidence and how the score would change without each feature group
    campaign(members, profiles, scores, ...)     what the members have in common, how tight the group is, which hard
                                                 links tie it, and why it was not merged with the nearest campaign
    assignment(assign_result, tau)               per campaign: did the new article join it, and on which rule
    decision_reasons(decision, neighbours, ...)  which rule of decision.decide() fired, with the numbers it compared

    python -m ads.explain 1 2 [--tau 0.6]        the pair explanation of two database cases as text
    python -m ads.explain --campaigns            every campaign with its signature and separation
"""
import argparse
import math
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import clustering, decision
from .clustering.linkage import _components
from .sim_functions import attributes as A
from .sim_functions import compare_all, load_config
from .sim_functions.aggregate import get
from .sim_functions.evidence import strong_links
from .sim_functions.normalize import norm, stem
from .sim_functions.primitives import name_similarity

# Feature groups, in display order. The same split as the channel ablation in robustness.py.
GROUPS = {
    "infrastructure": "infrastructure (trackers, redirect domains, endpoints and files, sponsoring page)",
    "core": "scam type and topic",
    "templates": "ad and landing-page templates, funnel",
    "persuasion": "persuasion devices",
    "entities": "product, people, companies, impersonated media",
    "text": "narrative, promise, call to action, summary, keywords",
    "surface": "props, amounts, dates, places",
}
# feature -> (group, how its values are compared and shown, path in the profile)
FEATURES: Dict[str, Tuple[str, str, str]] = {
    "tracker_ids": ("infrastructure", "anchor", "technical_artifacts.tracker_ids"),
    "redirect_chain_domains": ("infrastructure", "domains", "technical_artifacts.redirect_chain"),
    "dom_and_form_clues": ("infrastructure", "anchor", "technical_artifacts.dom_and_form_clues"),
    "ad_library_page_name": ("infrastructure", "enum", "technical_artifacts.ad_library_metadata.page_id_or_name"),
    "scam_type": ("core", "enum", "core_narrative.ad_goal_scam_type"),
    "topic": ("core", "enum", "core_narrative.topic"),
    "ad_creative_template": ("templates", "enum", "visual_and_production.ad_creative_template"),
    "landing_page_template": ("templates", "enum", "visual_and_production.landing_page_template"),
    "funnel_stages": ("templates", "set", "visual_and_production.funnel_stages"),
    "persuasion_devices": ("persuasion", "set", "core_narrative.persuasion_devices"),
    "product_name": ("entities", "product", "entities.product_or_platform"),
    "featured_people": ("entities", "people", "entities.featured_people"),
    "companies": ("entities", "names", "entities.companies_or_institutions"),
    "impersonated_media": ("entities", "names", "entities.impersonated_media"),
    "narrative": ("text", "text", "core_narrative.narrative_pattern"),
    "promise": ("text", "text", "core_narrative.promise_and_mechanism"),
    "call_to_action": ("text", "text", "core_narrative.call_to_action"),
    "embedding": ("text", "text", "canonical_comparison_text"),
    "keywords": ("text", "names", "core_narrative.keywords"),
    "setting_and_props": ("surface", "names", "visual_and_production.setting_and_props"),
    "amounts_dates_locations": ("surface", "amounts", "entities.amounts_dates_locations"),
}
EVIDENCE_KINDS = (("shared tracker ID", "tracker"), ("shared session/form endpoint", "endpoint"),
                  ("shared distinctive script/style file", "file"), ("shared domain", "domain"),
                  ("same sponsoring page", "page"))
MATCH = 0.5        # a pair of names/values counts as "shared" from this similarity on
MAX_ITEMS = 12     # values listed per side and feature
TEXT_CHARS = 280   # free text quoted per side


# ---------------------------------------------------------------- values behind one feature

def _person(p: Dict[str, Any]) -> str:
    return p.get("name") or f"unnamed {p.get('category_or_role') or 'person'}"


def _product(p: Optional[Dict[str, Any]]) -> Optional[str]:
    p = p or {}
    name, cat = p.get("exact_name"), p.get("generic_category")
    return f"{name} ({cat})" if name and cat else name or cat


def _greedy(xs: Sequence, ys: Sequence, sim, label=str) -> Dict[str, list]:
    """One-to-one matching, best pairs first (as in primitives.best_assignment): shared pairs and the leftovers."""
    pairs = sorted(((sim(x, y), i, j) for i, x in enumerate(xs) for j, y in enumerate(ys)), key=lambda t: -t[0])
    used_x, used_y, matches = set(), set(), []
    for s, i, j in pairs:
        if s < MATCH:
            break
        if i in used_x or j in used_y:
            continue
        used_x.add(i)
        used_y.add(j)
        matches.append({"a": label(xs[i]), "b": label(ys[j]), "similarity": round(s, 2)})
    return {"shared": matches[:MAX_ITEMS],
            "only_a": [label(x) for i, x in enumerate(xs) if i not in used_x][:MAX_ITEMS],
            "only_b": [label(y) for j, y in enumerate(ys) if j not in used_y][:MAX_ITEMS]}


def _sets(xs: Iterable, ys: Iterable) -> Dict[str, list]:
    sa, sb = {x for x in xs or [] if x}, {y for y in ys or [] if y}
    return {"shared": [{"a": v, "b": v, "similarity": 1.0} for v in sorted(sa & sb)][:MAX_ITEMS],
            "only_a": sorted(sa - sb)[:MAX_ITEMS], "only_b": sorted(sb - sa)[:MAX_ITEMS]}


def _text(a: Optional[str], b: Optional[str]) -> Dict[str, Any]:
    """Both texts and the words behind the stem overlap that text_similarity scores (without embeddings)."""
    def words(t):
        return [w for w in norm(t).split() if len(w) >= 4]
    stems_b = {stem(w) for w in words(b)}
    shared, seen = [], set()
    for w in words(a):
        if stem(w) in stems_b and stem(w) not in seen:
            seen.add(stem(w))
            shared.append(w)
    clip = lambda t: None if not t else (t if len(t) <= TEXT_CHARS else t[:TEXT_CHARS].rsplit(" ", 1)[0] + " …")  # noqa: E731
    return {"a": clip(a), "b": clip(b), "shared_words": shared[:MAX_ITEMS * 2]}


def _values(kind: str, va: Any, vb: Any, ignore: frozenset) -> Dict[str, Any]:
    if kind == "enum":
        return {"a": va, "b": vb}
    if kind == "product":
        return {"a": _product(va), "b": _product(vb)}
    if kind == "text":
        return _text(va, vb)
    if kind == "set":
        return _sets(va, vb)
    if kind == "anchor":
        return _sets([x for x in va or [] if x not in ignore], [y for y in vb or [] if y not in ignore])
    if kind == "domains":
        return _sets(A.domains(va), A.domains(vb))
    if kind == "people":
        return _greedy(va or [], vb or [], A._person_pair, _person)
    if kind == "names":
        return _greedy(va or [], vb or [], name_similarity)
    if kind == "amounts":
        va, vb = va or {}, vb or {}
        out = _greedy(va.get("amounts") or [], vb.get("amounts") or [], A._amount_pair)
        for key in ("dates", "locations"):
            part = _greedy(va.get(key) or [], vb.get(key) or [], name_similarity)
            for k in out:
                out[k] += part[k]
        return out
    return {}


def _empty(v: Any) -> bool:
    if isinstance(v, dict):
        return all(_empty(x) for x in v.values())
    return v is None or v == [] or (isinstance(v, str) and not v.strip())


# ---------------------------------------------------------------- one pair

def evidence_items(links: Sequence[str]) -> List[Dict[str, Any]]:
    """strong_links strings -> [{"kind", "value", "must_link", "text"}]; must_link = joins the pair on its own."""
    out = []
    for s in links:
        kind = next((k for prefix, k in EVIDENCE_KINDS if s.startswith(prefix)), "other")
        out.append({"kind": kind, "value": s.split(": ", 1)[1] if ": " in s else s,
                    "must_link": clustering.is_must_link({"strong_links": [s]}), "text": s})
    return out


def pair(a: Dict[str, Any], b: Dict[str, Any], tau: Optional[float] = None) -> Dict[str, Any]:
    """Full explanation of score(a, b). `features` and `groups` add up to `score` (contributions are shares of it);
    `loss` is how much a feature pulled the score below 1; `without` is the score with that group switched off
    (renormalised, like a missing feature). With `tau`, `crosses_tau` says whether switching the group off would
    move the pair across the threshold."""
    cfg = load_config()
    res = compare_all(a, b, weights=cfg["weights"], anchor_stats=cfg["anchor_stats"])
    ignore = frozenset(cfg["anchor_stats"].get("ignore") or ())
    s, total = round(res["score"] or 0.0, 4), res["used_weight"]
    feats, num, by_group = [], 0.0, {}
    for name, f in res["features"].items():
        group, kind, path = FEATURES.get(name, ("other", "", ""))
        va, vb = (get(a, path), get(b, path)) if path else (None, None)
        counted = f["contribution"] is not None
        row = {"feature": name, "group": group, "similarity": f["similarity"], "weight": f["weight"],
               "contribution": f["contribution"], "loss": None, "missing": None,
               "values": _values(kind, va, vb, ignore)}
        if counted:
            ws = f["weight"] * f["similarity"]
            num += ws
            row["loss"] = round(f["weight"] * (1 - f["similarity"]) / total, 4) if total else None
            g = by_group.setdefault(group, {"weight": 0.0, "ws": 0.0, "contribution": 0.0, "features": []})
            g["weight"] += f["weight"]
            g["ws"] += ws
            g["contribution"] += f["contribution"]
            g["features"].append(name)
        elif f["similarity"] is None:
            ea, eb = _empty(va), _empty(vb)
            row["missing"] = "both" if ea and eb else "a" if ea else "b" if eb else "unknown"
        feats.append(row)
    groups = []
    for key in list(GROUPS) + ["other"]:
        g = by_group.get(key)
        if not g:
            continue
        rest = total - g["weight"]
        without = round((num - g["ws"]) / rest, 4) if rest > 0 else None
        item = {"group": key, "contribution": round(g["contribution"], 4), "weight": round(g["weight"], 3),
                "similarity": round(g["ws"] / g["weight"], 4) if g["weight"] else None, "without": without,
                "features": g["features"]}
        if tau is not None and without is not None:
            item["crosses_tau"] = (s >= tau) != (without >= tau)
        groups.append(item)
    feats.sort(key=lambda r: (r["contribution"] is None, -(r["contribution"] or 0), r["feature"]))
    ev = evidence_items(strong_links(a, b))
    return {"score": s, "used_weight": total, "must_link": any(e["must_link"] for e in ev), "evidence": ev,
            "groups": groups, "features": feats, "tau": tau,
            "not_in_score": "demographics of unidentified people (never used for grouping)"}


# ---------------------------------------------------------------- one campaign

SIGNATURE = (("scam_type", "core_narrative.ad_goal_scam_type"), ("topic", "core_narrative.topic"),
             ("ad_creative_template", "visual_and_production.ad_creative_template"),
             ("landing_page_template", "visual_and_production.landing_page_template"),
             ("persuasion_devices", "core_narrative.persuasion_devices"),
             ("product_name", "entities.product_or_platform.exact_name"), ("featured_people", "entities.featured_people"),
             ("companies", "entities.companies_or_institutions"), ("impersonated_media", "entities.impersonated_media"),
             ("tracker_ids", "technical_artifacts.tracker_ids"),
             ("redirect_chain_domains", "technical_artifacts.redirect_chain"),
             ("dom_and_form_clues", "technical_artifacts.dom_and_form_clues"), ("keywords", "core_narrative.keywords"))


def _member_values(feature: str, raw: Any) -> Dict[str, str]:
    """{normalised value: shown value} of one member for one signature feature."""
    if raw is None:
        return {}
    if feature == "redirect_chain_domains":
        raw = A.domains(raw)
    items = raw if isinstance(raw, list) else [raw]
    out = {}
    for x in items:
        shown = _person(x) if isinstance(x, dict) else str(x)
        if isinstance(x, dict) and not x.get("name"):
            continue  # an unnamed person is not a shared identity
        key = norm(shown)
        if key:
            out.setdefault(key, shown)
    return out


def signature(members: Sequence[str], profiles: Dict[str, dict]) -> List[Dict[str, Any]]:
    """Values found in at least two members and in at least half of them, most widely shared first."""
    n = len(members)
    if n < 2:
        return []
    need = max(2, math.ceil(n / 2))
    out = []
    for feature, path in SIGNATURE:
        count, shown, who = Counter(), {}, {}
        for c in members:
            for key, val in _member_values(feature, get(profiles[c], path)).items():
                count[key] += 1
                shown.setdefault(key, val)
                who.setdefault(key, []).append(c)
        for key, k in count.items():
            if k >= need:
                out.append({"feature": feature, "group": FEATURES[feature][0], "value": shown[key], "count": k, "of": n,
                            "cases": who[key]})
    return sorted(out, key=lambda x: (-x["count"], list(GROUPS).index(x["group"]), x["feature"], x["value"]))


def campaign(members: Sequence[str], profiles: Dict[str, dict], scores: Dict[Tuple[str, str], Dict[str, Any]],
             tau: float, campaigns: Optional[Sequence[Sequence[str]]] = None) -> Dict[str, Any]:
    """Why these members form one campaign, and (given all `campaigns`) why it is separate from the nearest one."""
    members = list(members)
    pairs = [(x, y, clustering.pair(scores, x, y)) for i, x in enumerate(members) for y in members[i + 1:]]
    vals = [r["score"] for _, _, r in pairs]
    hard = [{"a": x, "b": y, "evidence": evidence_items(r["strong_links"])} for x, y, r in pairs
            if clustering.is_must_link(r)]
    out: Dict[str, Any] = {
        "members": members, "size": len(members), "signature": signature(members, profiles), "hard_links": hard,
        "cohesion": {"min": min(vals), "mean": round(sum(vals) / len(vals), 4), "max": max(vals)} if vals else None,
    }
    # parts held together by hard evidence alone (must-link components); several parts were merged by mean score
    parts = _components(members, [(h["a"], h["b"]) for h in hard])
    out["parts"] = [sorted(p) for p in sorted(parts, key=lambda p: (-len(p), sorted(p)))]
    out["rule"] = ("single case" if len(members) == 1 else "hard evidence" if len(parts) == 1 else
                   "hard evidence and mean score" if hard else "mean score")
    if len(parts) > 1:  # mean score between the parts (what average-link compared with tau)
        out["parts_mean"] = round(sum(clustering.average_score(p, q, scores) for i, p in enumerate(parts)
                                      for q in parts[i + 1:]) / (len(parts) * (len(parts) - 1) / 2), 4)
    if len(members) > 1:  # the member that holds on least: its mean score to the others
        weakest = min(members, key=lambda c: sum(clustering.pair(scores, c, o)["score"] for o in members if o != c))
        out["weakest"] = {"case": weakest, "mean": round(sum(clustering.pair(scores, weakest, o)["score"]
                                                              for o in members if o != weakest) / (len(members) - 1), 4)}
    others = [list(g) for g in campaigns or [] if set(g) != set(members)]
    if others:
        best = None
        for idx, g in enumerate(campaigns):
            if set(g) == set(members):
                continue
            mean = clustering.average_score(members, list(g), scores)
            top = max(((x, y, clustering.pair(scores, x, y)["score"]) for x in members for y in g), key=lambda t: t[2])
            if best is None or mean > best["mean"]:
                best = {"index": idx, "members": list(g), "mean": round(mean, 4),
                        "best_pair": {"a": top[0], "b": top[1], "score": top[2]},
                        "hard_evidence": any(clustering.is_must_link(clustering.pair(scores, x, y))
                                             for x in members for y in g)}
        best["gap"] = round(tau - best["mean"], 4)
        out["nearest"] = best
    return out


# ---------------------------------------------------------------- a new article against the campaigns

def assignment(assigned: Dict[str, Any], tau: float, top: int = 6) -> List[Dict[str, Any]]:
    """Per campaign (joined ones first, then by mean score): joined or not, on which rule, with the numbers.
    `assigned` is the result of clustering.assign() (needs its "scores" key)."""
    joined = [tuple(g) for g in assigned["joins"]]
    rows = []
    for g, d in assigned["group_scores"].items():
        res = {c: assigned["scores"][c] for c in g}
        hard = [{"case": c, "evidence": evidence_items(r["strong_links"])} for c, r in res.items()
                if clustering.is_must_link(r)]
        best = max(res.items(), key=lambda kv: kv[1]["score"])
        is_joined = tuple(g) in joined
        rows.append({"members": list(g), "mean": d["mean"], "gap": round(tau - d["mean"], 4), "hard": hard,
                     "best": {"case": best[0], "score": best[1]["score"]}, "joined": is_joined,
                     "rule": ("hard evidence" if hard else "mean score >= tau") if is_joined else "below tau"})
    rows.sort(key=lambda r: (not r["joined"], -r["mean"]))
    return rows[:max(top, len(joined))]


def decision_reasons(dec: Dict[str, Any], neighbours: Sequence[Tuple[str, Dict[str, Any]]], tau: float) -> Dict[str, Any]:
    """The rule of decision.decide() that produced `dec`, with every threshold and value it compared."""
    top_case, top = (neighbours[0][0], neighbours[0][1]) if neighbours else (None, None)
    return {"status": dec["status"], "rule": dec.get("rule"), "hard_case": dec.get("hard_case"), "top_case": top_case, "top_score": top["score"] if top else None,
            "evidence": evidence_items(top["strong_links"]) if top else [],
            "hard_score": dec.get("hard_score"), "hard_evidence": evidence_items(dec.get("hard_links") or []),
            "thresholds": {"tau": tau, "family": decision.FAMILY_SCORE, "confirm": decision.CONFIRM_SCORE},
            "duplicates": [{"case": d["case"], "reasons": d["reasons"]} for d in dec.get("related") or []]
            if dec["status"] in ("duplicate", "same_content") else []}


# ---------------------------------------------------------------- command line

def format_pair(ex: Dict[str, Any], ida: str = "a", idb: str = "b") -> str:
    lines = [f"{ida} <-> {idb}: score {ex['score']:.2f}" + ("  (hard evidence: joined whatever the score)"
                                                             if ex["must_link"] else "")]
    for e in ex["evidence"]:
        lines.append(f"  evidence  {e['text']}" + ("  [must-link]" if e["must_link"] else ""))
    lines.append("  by group                         share   similarity   score without it")
    for g in ex["groups"]:
        cross = "  <- crosses tau" if g.get("crosses_tau") else ""
        wo = "n/a" if g["without"] is None else f"{g['without']:.2f}"
        lines.append(f"    {g['group']:<28} {g['contribution']:>6.2f}   {g['similarity']:>9.2f}   {wo:>8}{cross}")
    lines.append("  features (contribution, similarity, shared / only here / only there)")
    for f in ex["features"]:
        v = f["values"]
        if f["contribution"] is None:
            if f["missing"]:
                lines.append(f"    {f['feature']:<24} not comparable (no data: {f['missing']})")
            continue
        shared = ", ".join(m["a"] if m["a"] == m["b"] else f"{m['a']} ~ {m['b']}" for m in v.get("shared", []))
        if "shared_words" in v:
            shared = ", ".join(v["shared_words"][:8])
        if "a" in v and "shared" not in v and "shared_words" not in v:
            shared = f"{v['a']} | {v['b']}"
        lines.append(f"    {f['feature']:<24} {f['contribution']:>5.2f} {f['similarity']:>5.2f}  {shared[:90]}")
    return "\n".join(lines)


def main() -> None:
    from .evaluate import load_profiles, require_profiles
    ap = argparse.ArgumentParser(description="Explain why cases are linked")
    ap.add_argument("cases", nargs="*", help="two case ids")
    ap.add_argument("--tau", type=float, default=0.6)
    ap.add_argument("--campaigns", action="store_true", help="explain every campaign at tau")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    profiles = require_profiles(load_profiles())
    if a.campaigns:
        from .analyze import campaigns as group, pair_table
        scores, groups = pair_table(profiles), group(profiles, a.tau)
        for i, g in enumerate(groups, 1):
            ex = campaign(g, profiles, scores, a.tau, groups)
            parts = " | ".join(",".join(p) for p in ex.get("parts", []))
            print(f"K{i}: {', '.join(g)}  rule: {ex['rule']} [{parts}]" + (f"  cohesion min {ex['cohesion']['min']:.2f} "
                                                                  f"mean {ex['cohesion']['mean']:.2f}" if ex["cohesion"] else ""))
            for s in ex["signature"]:
                print(f"    shared {s['feature']}: {s['value']} ({s['count']}/{s['of']})")
            n = ex.get("nearest")
            if n:
                print(f"    nearest other: {', '.join(n['members'])} mean {n['mean']:.2f} (tau {a.tau}), "
                      f"best pair {n['best_pair']['a']}-{n['best_pair']['b']} {n['best_pair']['score']:.2f}")
        return
    if len(a.cases) != 2 or any(c not in profiles for c in a.cases):
        sys.exit(f"give two case ids from: {', '.join(sorted(profiles))}")
    print(format_pair(pair(profiles[a.cases[0]], profiles[a.cases[1]], a.tau), *a.cases))


if __name__ == "__main__":
    main()
