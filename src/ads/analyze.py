"""Analyse one new article against the database, with no UI code (the panel calls this; tests use MockClient).

    case, notes = case_from_url("https://...", pasted_text="")
    result = analyse(case, profiles, tau, client)       # profile, duplicates, neighbours, joins, decision, llm_used
    groups = groups_overview(profiles, tau)              # campaigns with their family, members and linking evidence
    cid = save_case(case, result["profile"], result["decision"])
"""
import json
import os
import shutil
from collections import Counter
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from . import clustering, decision, dedup
from .paths import CASES, DATA
from .preprocess.har import host, reg_domain

EMPTY_TECH = {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [], "dom_and_form_clues": [],
              "domain_and_cert_metadata": []}
CAPTURE_REASONS = ("near-identical image", "same final URL")  # the same capture again (see decision.py)


def case_from_url(url: str, pasted_text: str = "") -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """In-memory case_input for an article: the scanned page (text + technical traces) plus any pasted text.

    Returns (None, notes) when there is no text at all. Pasted text helps when the page needs JavaScript or
    shows reviewers a neutral page (cloaking)."""
    notes: List[str] = []
    text, tech = "", dict(EMPTY_TECH)
    if url.strip():
        from .preprocess.url_scan import scan_url
        scan = scan_url(url.strip())
        if scan["ok"]:
            text, tech = scan["text"], scan["technical_summary"]
            notes += scan["notes"]
            if scan["final_url"].rstrip("/") != url.strip().rstrip("/"):
                notes.append(f"redirected to {scan['final_url']}")
        else:
            notes.append(f"could not fetch the page: {scan['error']}")
    text = "\n".join(t for t in (text, pasted_text.strip()) if t)
    if not text:
        return None, notes
    case = {"schema_version": "1.0", "case_id": "new",
            "parts": [{"role": "bridge_page", "medium": "text", "text": text, "images": []}],
            "technical_summary": tech, "resolved_identities": []}
    return case, notes


def analyse(case: Dict[str, Any], profiles: Dict[str, dict], tau: float, client=None,
            variants: Optional[Dict[str, List[dict]]] = None,
            fingerprints: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Duplicate check first; a repeat capture reuses the stored profile, so it costs no LLM call.
    `fingerprints` defaults to those of the cases on disk (dedup.load_fingerprints)."""
    fps = fingerprints if fingerprints is not None else dedup.load_fingerprints()
    fps = {k: v for k, v in fps.items() if k in profiles}
    dups = dedup.find_duplicates(dedup.fingerprint(case), fps)
    repeat = next((d["case"] for d in dups if any(r.startswith(CAPTURE_REASONS) for r in d["reasons"])), None)
    if repeat:
        profile = profiles[repeat]
    else:
        from .llm.extract import extract
        profile = extract(case, client)
    res = clustering.assign(profile, profiles, tau, variants=variants)
    return {"profile": profile, "duplicates": dups, "neighbours": res["neighbours"], "joins": res["joins"],
            "decision": decision.decide(res["neighbours"], dups, likely=tau), "llm_used": not repeat}


def groups_overview(profiles: Dict[str, dict], tau: float, family_tau: float = decision.FAMILY_SCORE,
                    variants: Optional[Dict[str, List[dict]]] = None) -> List[Dict[str, Any]]:
    """Campaigns at tau, largest family first; each with its family number, members and the evidence that links them."""
    scores = clustering.pair_scores(profiles, variants)
    campaigns = clustering.cluster(profiles, tau, scores)
    out = []
    for fam_no, family in enumerate(clustering.hierarchy(profiles, campaigns, family_tau, scores), 1):
        for ci in family:
            members = campaigns[ci]
            links = [{"a": a, "b": b, "score": clustering.pair(scores, a, b)["score"],
                      "evidence": clustering.pair(scores, a, b)["strong_links"]} for a, b in combinations(members, 2)]
            scam = Counter(profiles[c]["core_narrative"]["ad_goal_scam_type"] for c in members).most_common(1)[0][0]
            out.append({"family": fam_no, "members": members, "scam_type": scam,
                        "links": sorted(links, key=lambda x: -x["score"])})
    return out


def case_summary(cid: str, p: Dict[str, Any]) -> Dict[str, Any]:
    """What an analyst wants to see about one case, flattened from its profile and case_input."""
    n, e, v, ta = p["core_narrative"], p["entities"], p["visual_and_production"], p["technical_artifacts"]
    urls = (ta.get("redirect_chain") or []) + (ta.get("urls_and_domains") or [])
    return {
        "case": cid, "scam_type": n["ad_goal_scam_type"], "topic": n["topic"],
        "product": e["product_or_platform"].get("exact_name") or e["product_or_platform"].get("generic_category"),
        "people": [x.get("name") or f"unnamed {x.get('category_or_role')}" for x in e["featured_people"]],
        "media": e["impersonated_media"], "companies": e["companies_or_institutions"],
        "templates": f"{v['ad_creative_template'] or 'no ad'} -> {v['landing_page_template'] or 'no page'}",
        "persuasion": n["persuasion_devices"], "summary": p["canonical_comparison_text"],
        "domains": sorted({reg_domain(host(u)) for u in urls if host(u)}), "trackers": ta.get("tracker_ids") or [],
        "image": first_image(cid),
    }


def first_image(cid: str) -> Optional[str]:
    """Absolute path of the case's first screenshot or video contact sheet, if any."""
    f = os.path.join(CASES, cid, "case_input.json")
    if not os.path.exists(f):
        return None
    for part in json.load(open(f, encoding="utf-8"))["parts"]:
        for img in part.get("images", []):
            path = img if os.path.isabs(img) else os.path.join(DATA, img)
            if os.path.exists(path):
                return path
    return None


def save_case(case: Dict[str, Any], profile: Dict[str, Any], dec: Optional[Dict[str, Any]] = None,
              cases_dir: str = CASES) -> str:
    """Store the analysed article as <cases_dir>/web_<n>/ so later articles are compared with it (gitignored)."""
    n = 1
    while os.path.exists(os.path.join(cases_dir, f"web_{n}")):
        n += 1
    cid = f"web_{n}"
    d = os.path.join(cases_dir, cid)
    os.makedirs(d)
    case = json.loads(json.dumps(case))
    case["case_id"] = cid
    for part in case["parts"]:
        saved = []
        for img in part.get("images", []):
            shutil.copy(img, os.path.join(d, os.path.basename(img)))
            saved.append(f"cases/{cid}/{os.path.basename(img)}")
        part["images"] = saved
    status = (dec or {}).get("status")
    meta: Dict[str, Any] = {"decision": status}
    if status == "duplicate":
        meta["duplicate_of"] = dec["join"][0]
    elif status in ("new_unconfirmed", "suggested_family", "likely"):
        meta["status"] = "unconfirmed"  # an analyst confirms it later
    for name, data in (("case_input.json", case), ("profile.json", profile), ("meta.json", meta)):
        json.dump(data, open(os.path.join(d, name), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return cid
