"""Graded decision for a case compared with the database (replaces the binary "joins a group / new group").

    d = decide(neighbours, duplicates, likely=0.55)
    d["status"], d["title"], d["explanation"], d["matches"], d["related"]

Statuses, strongest first:
  duplicate          same capture again (near-identical image or same final URL): attach, do not count as new
  same_content       identical/near-identical page text on another host: same campaign, different infrastructure
  confirmed          score >= likely AND hard evidence (tracker, domain, sender page, shared platform endpoints),
                     or score >= confirm_score, or must-link evidence with any case (`hard`, the same rule that joins
                     a campaign in clustering, so the verdict never contradicts the campaign the article joins)
  likely             score >= likely but no hard evidence
  suggested_family   score >= family: related to a known family, too weak to call it the same campaign
  new_unconfirmed    nothing close: a new campaign candidate, to be confirmed by an analyst

The missing-data tests showed that a case with only an ad creative scores below the usual threshold yet still has
the right family as its nearest neighbour; `suggested_family` exists for exactly that situation.
Every result has "rule": the condition that fired (capture, content, empty, score_confirm, tau_and_evidence,
hard_evidence, tau_only, family, nothing), which the panel and explain.decision_reasons show.
"""
from typing import Any, Dict, List, Optional, Tuple

CONFIRM_SCORE = 0.80
FAMILY_SCORE = 0.30


def _top(neighbours: List[Tuple[str, Dict[str, Any]]], n: int = 3) -> List[Dict[str, Any]]:
    return [{"case": c, "score": r["score"], "strong_links": r["strong_links"]} for c, r in neighbours[:n]]


def decide(neighbours: List[Tuple[str, Dict[str, Any]]], duplicates: List[Dict[str, Any]],
           likely: float = 0.55, family: float = FAMILY_SCORE, confirm: float = CONFIRM_SCORE,
           hard: Optional[List[Tuple[str, Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """`hard`: (case, score result) of every database case with must-link evidence to this one (may be empty)."""
    matches = _top(neighbours)
    capture = [d for d in duplicates if any(r.startswith(("near-identical image", "same final URL")) for r in d["reasons"])]
    if capture:
        d = capture[0]
        return {"status": "duplicate", "rule": "capture", "title": f"Duplicate of case {d['case']}",
                "explanation": "Same capture seen before (" + "; ".join(d["reasons"]) + "). It is attached to that record, not counted as new.",
                "join": [d["case"]], "matches": matches, "related": duplicates}
    if duplicates:
        d = duplicates[0]
        return {"status": "same_content", "rule": "content", "title": f"Same content as case {d['case']} on another host: same campaign",
                "explanation": "Matching content (" + " / ".join(d["reasons"]) + ") but the technical traces differ, "
                               "which is typical of one campaign re-hosted on new domains.",
                "join": [x["case"] for x in duplicates], "matches": matches, "related": duplicates}
    if not neighbours:
        return {"status": "new_unconfirmed", "rule": "empty", "title": "New campaign (unconfirmed)",
                "explanation": "The database is empty.",
                "join": [], "matches": [], "related": []}
    cid, top = neighbours[0]
    s, strong = top["score"], top["strong_links"]
    if s >= confirm or (s >= likely and strong):
        ev = ("; ".join(strong) if strong else f"score {s:.2f}")
        return {"status": "confirmed", "rule": "score_confirm" if s >= confirm else "tau_and_evidence",
                "title": f"Confirmed: same campaign as case {cid}",
                "explanation": f"Score {s:.2f} with hard evidence: {ev}.",
                "join": [c for c, r in neighbours if r["score"] >= likely], "matches": matches, "related": []}
    if hard:
        hc, hr = max(hard, key=lambda kv: kv[1]["score"])
        return {"status": "confirmed", "rule": "hard_evidence", "hard_case": hc, "hard_score": hr["score"],
                "hard_links": hr["strong_links"],
                "title": f"Confirmed: same campaign as case {hc}",
                "explanation": f"Hard evidence with case {hc} ({'; '.join(hr['strong_links'])}) joins it to that "
                               f"campaign whatever the content score ({hr['score']:.2f}).",
                "join": [hc], "matches": matches, "related": []}
    if s >= likely:
        return {"status": "likely", "rule": "tau_only", "title": f"Likely the same campaign as case {cid}",
                "explanation": f"Score {s:.2f} from similar content, but no hard technical evidence (tracker, domain, "
                               "platform endpoints). An analyst should confirm.",
                "join": [c for c, r in neighbours if r["score"] >= likely], "matches": matches, "related": []}
    if s >= family:
        return {"status": "suggested_family", "rule": "family", "title": f"Possibly related to case {cid}: treat as unconfirmed",
                "explanation": f"Best score {s:.2f} is below the threshold {likely:.2f}. The material resembles a known family "
                               "but there is not enough to call it the same campaign (this is also what an ad shown without "
                               "its landing page looks like).",
                "join": [], "matches": matches, "related": []}
    return {"status": "new_unconfirmed", "rule": "nothing", "title": "New campaign (unconfirmed)",
            "explanation": f"Nothing in the database is close (best score {s:.2f}).", "join": [], "matches": matches, "related": []}
