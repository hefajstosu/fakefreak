"""A new article against the database: duplicates, nearest cases, campaigns and families joined, the verdict and why."""
from typing import Any, Dict, Optional

from .. import clustering, decision, dedup, explain
from .index import campaigns, families

CAPTURE_REASONS = ("near-identical image", "same final URL")  # the same capture again (see decision.py)


def _fingerprints(profiles: Dict[str, dict], fingerprints: Optional[Dict[str, dict]]) -> Dict[str, dict]:
    fps = fingerprints if fingerprints is not None else dedup.load_fingerprints()
    return {k: v for k, v in fps.items() if k in profiles}


def compare(profile: Dict[str, Any], fingerprint: Optional[Dict[str, Any]], profiles: Dict[str, dict], tau: float,
            fingerprints: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Compare a profile with the database (no LLM). Returns duplicates (of `fingerprint`, a dedup.fingerprint or
    None), neighbours, the campaigns it joins, the graded decision and why: "reasons" (the decision rule and its
    numbers), "campaigns" (per campaign: joined or not, on which rule), "families" and "family_joins".
    `fingerprints` defaults to those of the cases on disk."""
    dups = dedup.find_duplicates(fingerprint, _fingerprints(profiles, fingerprints)) if fingerprint else []
    res = clustering.assign(profile, profiles, tau, groups=campaigns(profiles, tau))
    hard = [(c, r) for c, r in res["scores"].items() if clustering.is_must_link(r)]
    fam = explain.family_assignment(profile, res["scores"], families(profiles, tau), profiles)
    fam_links = [(c, res["scores"][c]) for row in fam for c in row["evidence_with"]]
    dec = decision.decide(res["neighbours"], dups, likely=tau, hard=hard, family_links=fam_links)
    return {"duplicates": dups, "neighbours": res["neighbours"], "joins": res["joins"], "decision": dec,
            "reasons": explain.decision_reasons(dec, res["neighbours"], tau),
            "campaigns": explain.assignment(res, tau), "families": fam,
            "family_joins": [row["members"] for row in fam if row["joined"]]}


def analyse(case: Dict[str, Any], profiles: Dict[str, dict], tau: float, client=None,
            fingerprints: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Profile the case with the LLM and compare it. A repeat capture (same image or final URL as a database case)
    reuses that case's profile, so it costs no LLM call. Returns compare()'s keys plus "profile" and "llm_used"."""
    fps = _fingerprints(profiles, fingerprints)
    fp = dedup.fingerprint(case)
    repeat = next((d["case"] for d in dedup.find_duplicates(fp, fps)
                   if any(r.startswith(CAPTURE_REASONS) for r in d["reasons"])), None)
    if repeat:
        profile = profiles[repeat]
    else:
        from ..llm.extract import extract
        profile = extract(case, client)
    return {"profile": profile, "llm_used": not repeat, **compare(profile, fp, profiles, tau, fps)}
