"""A new article against the campaigns and families: joined or not, on which rule, and why the verdict."""
from typing import Any, Dict, List, Sequence, Tuple

from .. import clustering, decision
from ..sim_functions import get
from .catalog import evidence_items


def assignment(assigned: Dict[str, Any], tau: float, top: int = 6) -> List[Dict[str, Any]]:
    """Per campaign (joined first, then by mean score): joined or not and on which rule (hard evidence, same content,
    mean score >= tau, below tau), with the numbers. `assigned` is a clustering.assign() result."""
    joined = [tuple(g) for g in assigned["joins"]]
    rows = []
    for g, d in assigned["group_scores"].items():
        res = {c: assigned["scores"][c] for c in g}
        hard = [{"case": c, "evidence": evidence_items(r["strong_links"])} for c, r in res.items()
                if clustering.is_must_link(r)]
        best = max(res.items(), key=lambda kv: kv[1]["score"])
        is_joined = tuple(g) in joined
        rule = ("hard evidence" if hard else "same content" if best[1]["score"] >= clustering.SAME_CONTENT_SCORE
                else "mean score >= tau") if is_joined else "below tau"
        rows.append({"members": list(g), "mean": d["mean"], "gap": round(tau - d["mean"], 4), "hard": hard,
                     "best": {"case": best[0], "score": best[1]["score"]}, "joined": is_joined, "rule": rule})
    rows.sort(key=lambda r: (not r["joined"], -r["mean"]))
    return rows[:max(top, len(joined))]


def family_assignment(profile: Dict[str, Any], scores: Dict[str, Dict[str, Any]], families: Sequence[Sequence[str]],
                      profiles: Dict[str, dict], family_tau: float = decision.FAMILY_SCORE,
                      top: int = 4) -> List[Dict[str, Any]]:
    """Per family: does the new article belong to it by the rule of clustering.hierarchy (same scam type and a score
    >= family_tau, or family-level evidence), and with which cases."""
    scam = get(profile, "core_narrative.ad_goal_scam_type")
    rows = []
    for fam in families:
        same = [c for c in fam if get(profiles[c], "core_narrative.ad_goal_scam_type") == scam]
        by_score = [c for c in same if scores[c]["score"] >= family_tau]
        by_evidence = [c for c in same if clustering.is_family_link(scores[c])]
        best = max(fam, key=lambda c: scores[c]["score"])
        rows.append({"members": list(fam), "joined": bool(by_score or by_evidence), "score_with": by_score,
                     "evidence_with": by_evidence, "best": {"case": best, "score": scores[best]["score"]}})
    rows.sort(key=lambda r: (not r["joined"], -r["best"]["score"]))
    return rows[:max(top, sum(r["joined"] for r in rows))]


def decision_reasons(dec: Dict[str, Any], neighbours: Sequence[Tuple[str, Dict[str, Any]]], tau: float) -> Dict[str, Any]:
    """The rule of decision.decide() that produced `dec`, with every threshold and value it compared."""
    top_case, top = neighbours[0] if neighbours else (None, None)
    return {"status": dec["status"], "rule": dec.get("rule"), "top_case": top_case,
            "top_score": top["score"] if top else None, "evidence": evidence_items(top["strong_links"]) if top else [],
            "hard_case": dec.get("hard_case"), "hard_score": dec.get("hard_score"),
            "hard_evidence": evidence_items(dec.get("hard_links") or []),
            "family_case": dec.get("family_case"), "family_score": dec.get("family_score"),
            "family_evidence": evidence_items(dec.get("family_links") or []),
            "thresholds": {"tau": tau, "family": decision.FAMILY_SCORE, "confirm": decision.CONFIRM_SCORE},
            "duplicates": [{"case": d["case"], "reasons": d["reasons"]} for d in dec.get("related") or []]
            if dec["status"] in ("duplicate", "same_content") else []}
