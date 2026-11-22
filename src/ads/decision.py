"""Graded decision for a case compared with the database (replaces the binary "joins a group / new group").

    d = decide(neighbours, duplicates, likely=0.55)
    d["status"], d["title"], d["explanation"], d["matches"], d["related"]

Statuses, strongest first:
  duplicate          same capture again (near-identical image or same final URL): attach, do not count as new
  same_content       identical/near-identical page text on another host: same campaign, different infrastructure
  confirmed          score >= likely AND hard evidence (tracker, domain, sender page, shared platform endpoints),
                     or score >= confirm_score
  likely             score >= likely but no hard evidence
  suggested_family   score >= family: related to a known family, too weak to call it the same campaign
  new_unconfirmed    nothing close: a new campaign candidate, to be confirmed by an analyst

The missing-data tests showed that a case with only an ad creative scores below the usual threshold yet still has
the right family as its nearest neighbour; `suggested_family` exists for exactly that situation.
"""
from typing import Any, Dict, List, Tuple

CONFIRM_SCORE = 0.80
FAMILY_SCORE = 0.30


def _top(neighbours: List[Tuple[str, Dict[str, Any]]], n: int = 3) -> List[Dict[str, Any]]:
    return [{"case": c, "score": r["score"], "strong_links": r["strong_links"]} for c, r in neighbours[:n]]


def decide(neighbours: List[Tuple[str, Dict[str, Any]]], duplicates: List[Dict[str, Any]],
           likely: float = 0.55, family: float = FAMILY_SCORE, confirm: float = CONFIRM_SCORE) -> Dict[str, Any]:
    matches = _top(neighbours)
    capture = [d for d in duplicates if any(r.startswith(("near-identical image", "same final URL")) for r in d["reasons"])]
    if capture:
        d = capture[0]
        return {"status": "duplicate", "title": f"Duplicate of case {d['case']}",
                "explanation": "Same capture seen before (" + "; ".join(d["reasons"]) + "). It is attached to that record, not counted as new.",
                "join": [d["case"]], "matches": matches, "related": duplicates}
    if duplicates:
        d = duplicates[0]
        return {"status": "same_content", "title": f"Same content as case {d['case']} on another host: same campaign",
                "explanation": "Matching content (" + " / ".join(d["reasons"]) + ") but the technical traces differ, "
                               "which is typical of one campaign re-hosted on new domains.",
                "join": [x["case"] for x in duplicates], "matches": matches, "related": duplicates}
    if not neighbours:
        return {"status": "new_unconfirmed", "title": "New campaign (unconfirmed)", "explanation": "The database is empty.",
                "join": [], "matches": [], "related": []}
    cid, top = neighbours[0]
    s, strong = top["score"], top["strong_links"]
    if s >= confirm or (s >= likely and strong):
        ev = ("; ".join(strong) if strong else f"score {s:.2f}")
        return {"status": "confirmed", "title": f"Confirmed: same campaign as case {cid}",
                "explanation": f"Score {s:.2f} with hard evidence: {ev}.",
                "join": [c for c, r in neighbours if r["score"] >= likely], "matches": matches, "related": []}
    if s >= likely:
        return {"status": "likely", "title": f"Likely the same campaign as case {cid}",
                "explanation": f"Score {s:.2f} from similar content, but no hard technical evidence (tracker, domain, "
                               "platform endpoints). An analyst should confirm.",
                "join": [c for c, r in neighbours if r["score"] >= likely], "matches": matches, "related": []}
    if s >= family:
        return {"status": "suggested_family", "title": f"Possibly related to case {cid}: treat as unconfirmed",
                "explanation": f"Best score {s:.2f} is below the threshold {likely:.2f}. The material resembles a known family "
                               "but there is not enough to call it the same campaign (this is also what an ad shown without "
                               "its landing page looks like).",
                "join": [], "matches": matches, "related": []}
    return {"status": "new_unconfirmed", "title": "New campaign (unconfirmed)",
            "explanation": f"Nothing in the database is close (best score {s:.2f}).", "join": [], "matches": matches, "related": []}
