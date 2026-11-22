"""Graded decision for a case compared with the database (replaces the binary "joins a group / new group").

    d = decide(neighbours, duplicates, tau=0.6, hard=..., family_links=...)
    d["status"], d["rule"], d["title"], d["explanation"]

Statuses, strongest first:
  duplicate          same capture again (near-identical image or same final URL): attach, do not count as new
  same_content       identical/near-identical page text on another host: same campaign, different infrastructure
  confirmed          the top case scores >= SAME_CONTENT_SCORE, or must-link evidence (clustering/evidence.py) with
                     any case: the same rules that join a campaign in clustering
  likely             score >= tau but no must-link evidence
  suggested_family   family-level evidence (shared tool, page kit or tracking template, same scam type) with any case,
                     or score >= FAMILY_SCORE: related to a known family, too weak to call it the same campaign
  new_unconfirmed    nothing close: a new campaign candidate, to be confirmed by an analyst

The missing-data tests showed that a case with only an ad creative scores below the usual threshold yet still has
the right family as its nearest neighbour; `suggested_family` exists for exactly that situation.
Every result has "rule": the condition that fired (capture, content, empty, score_confirm, tau_and_evidence,
hard_evidence, tau_only, family_evidence, family, nothing), which the panel and explain.decision_reasons show.
"""
from typing import Any, Dict, List, Optional, Tuple

from .clustering import FAMILY_SCORE, SAME_CONTENT_SCORE, TAU, is_must_link
from .dedup import CAPTURE_REASONS

Scored = List[Tuple[str, Dict[str, Any]]]  # (case id, similarity.score result)


def decide(neighbours: Scored, duplicates: List[Dict[str, Any]], tau: float = TAU,
           hard: Optional[Scored] = None, family_links: Optional[Scored] = None) -> Dict[str, Any]:
    """`neighbours`: database cases by score, best first. `duplicates`: dedup.find_duplicates of this case.
    `hard`: every case with must-link evidence to this one; `family_links`: every case with family-level evidence."""
    capture = [d for d in duplicates if any(r.startswith(CAPTURE_REASONS) for r in d["reasons"])]
    if capture:
        d = capture[0]
        return {"status": "duplicate", "rule": "capture", "duplicate_of": d["case"], "related": duplicates,
                "title": f"Duplicate of case {d['case']}",
                "explanation": "Same capture seen before (" + "; ".join(d["reasons"]) + "). It is attached to that record, not counted as new."}
    if duplicates:
        d = duplicates[0]
        return {"status": "same_content", "rule": "content", "related": duplicates,
                "title": f"Same content as case {d['case']} on another host: same campaign",
                "explanation": "Matching content (" + " / ".join(d["reasons"]) + ") but the technical traces differ, "
                               "which is typical of one campaign re-hosted on new domains."}
    if not neighbours:
        return {"status": "new_unconfirmed", "rule": "empty", "title": "New campaign (unconfirmed)",
                "explanation": "The database is empty."}
    cid, top = neighbours[0]
    s = top["score"]
    if s >= SAME_CONTENT_SCORE or (s >= tau and is_must_link(top)):
        return {"status": "confirmed", "rule": "score_confirm" if s >= SAME_CONTENT_SCORE else "tau_and_evidence",
                "title": f"Confirmed: same campaign as case {cid}",
                "explanation": f"Score {s:.2f} with " + ("; ".join(top["strong_links"]) or "near-identical content") + "."}
    if hard:
        hc, hr = max(hard, key=lambda kv: kv[1]["score"])
        return {"status": "confirmed", "rule": "hard_evidence", "hard_case": hc, "hard_score": hr["score"],
                "hard_links": hr["strong_links"], "title": f"Confirmed: same campaign as case {hc}",
                "explanation": f"Hard evidence with case {hc} ({'; '.join(hr['strong_links'])}) joins it to that "
                               f"campaign whatever the content score ({hr['score']:.2f})."}
    if s >= tau:
        return {"status": "likely", "rule": "tau_only", "title": f"Likely the same campaign as case {cid}",
                "explanation": f"Score {s:.2f} from similar content, but no hard evidence (tracker, sponsoring page, "
                               "ad campaign ID, certificate). An analyst should confirm."}
    if family_links:
        fc, fr = max(family_links, key=lambda kv: kv[1]["score"])
        return {"status": "suggested_family", "rule": "family_evidence", "family_case": fc, "family_score": fr["score"],
                "family_links": fr["strong_links"], "title": f"Same family as case {fc}, unconfirmed as the same campaign",
                "explanation": f"Family evidence with case {fc} ({'; '.join(fr['strong_links'])}): the same tool, page "
                               f"kit or tracking template and the same scam type; the content score ({fr['score']:.2f}) "
                               "is too low to call it the same campaign."}
    if s >= FAMILY_SCORE:
        return {"status": "suggested_family", "rule": "family", "title": f"Possibly related to case {cid}: treat as unconfirmed",
                "explanation": f"Best score {s:.2f} is below the threshold {tau:.2f}. The material resembles a known family "
                               "but there is not enough to call it the same campaign (this is also what an ad shown without "
                               "its landing page looks like)."}
    return {"status": "new_unconfirmed", "rule": "nothing", "title": "New campaign (unconfirmed)",
            "explanation": f"Nothing in the database is close (best score {s:.2f})."}
