"""Analyse new material against the database, with no UI code. The web panel and the Streamlit demo both use it.

Three steps, each usable on its own:

    case, notes = build_case(url="https://...", text="", images=[], html_files=[])   # material -> case_input
    result = analyse(case, profiles, tau, client)    # duplicate check, LLM profile (skipped for a repeat), compare
    result = compare(profile, fingerprint, profiles, tau)   # duplicates, nearest cases, campaigns joined, decision

and for display and storage:

    groups = groups_overview(profiles, tau)          # campaigns with their family, members and linking evidence
    scores = pair_table(profiles)                    # the N x N pair table, reused between calls (see its docstring)
    summary = case_summary(case_id, profile)         # one case, flattened for a card
    cid = save_case(case, result["profile"], result["decision"])
"""
import hashlib
import json
import os
import shutil
from collections import Counter
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import clustering, decision, dedup
from .paths import CASES, DATA
from .preprocess.har import host, reg_domain

EMPTY_TECH = {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [], "dom_and_form_clues": [],
              "domain_and_cert_metadata": []}
CAPTURE_REASONS = ("near-identical image", "same final URL")  # the same capture again (see decision.py)


# ---------------------------------------------------------------- step 1: material -> case_input

def build_case(url: str = "", text: str = "", images: Sequence[str] = (), html_files: Sequence[str] = (),
               product: str = "", text_role: str = "bridge_page") -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """In-memory case_input from what an analyst has: a URL (scanned for text and technical traces), pasted text,
    screenshot paths, saved HTML pages and a product name. Returns (None, notes) when nothing usable is given.

    Screenshots become the ad creative, each HTML file a bridge page, and the scanned plus pasted text one more page
    with role `text_role` (default: a bridge page, i.e. the fake article)."""
    notes: List[str] = []
    tech = dict(EMPTY_TECH)
    page_text = text.strip()
    if url.strip():
        from .preprocess.url_scan import scan_url
        scan = scan_url(url.strip())
        if scan["ok"]:
            page_text = "\n".join(t for t in (scan["text"], page_text) if t)
            tech = scan["technical_summary"]
            notes += scan["notes"]
            if scan["final_url"].rstrip("/") != url.strip().rstrip("/"):
                notes.append(f"redirected to {scan['final_url']}")
        else:
            notes.append(f"could not fetch the page: {scan['error']}")
    if product.strip():
        page_text = f"Product or platform named by the analyst: {product.strip()}\n" + page_text
    parts: List[Dict[str, Any]] = []
    if images:
        parts.append({"role": "ad_creative", "medium": "image", "text": None, "images": list(images)})
    if html_files:
        from .preprocess.assemble import html_to_text
        parts += [{"role": "bridge_page", "medium": "html", "text": html_to_text(p), "images": []} for p in html_files]
    if page_text.strip():
        parts.append({"role": text_role, "medium": "text", "text": page_text.strip(), "images": []})
    if not parts:
        return None, notes
    return {"schema_version": "1.0", "case_id": "new", "parts": parts, "technical_summary": tech,
            "resolved_identities": []}, notes


# ---------------------------------------------------------------- the pair table, reused between analyses

_PAIRS: Dict[Tuple[str, ...], Dict[str, Any]] = {}  # (sha a, sha b, variants sha a, variants sha b) -> pair result


def _sha(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def pair_table(profiles: Dict[str, dict],
               variants: Optional[Dict[str, List[dict]]] = None) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """clustering.pair_scores(profiles, variants), with every pair remembered by the content of its two profiles
    (and their variants). A long-running panel therefore compares a pair once: after a case is saved the next
    analysis costs N new comparisons instead of N*(N-1)/2. Results keep only "score", "base", "via_variant" and
    "strong_links", which is all the grouping reads. The memory holds about twice the current table at most."""
    variants = variants or {}
    shas = {c: _sha(p) for c, p in profiles.items()}
    vshas = {c: _sha(variants[c]) if variants.get(c) else "" for c in profiles}
    table = {}
    for a, b in combinations(sorted(profiles), 2):
        key = (shas[a], shas[b], vshas[a], vshas[b])
        if key not in _PAIRS:
            r = clustering.best_score(profiles[a], profiles[b], variants.get(a), variants.get(b))
            _PAIRS[key] = {k: r[k] for k in ("score", "base", "via_variant", "strong_links")}
        table[(a, b)] = _PAIRS[key]
    if len(_PAIRS) > 2 * len(table) + 1000:  # drop pairs of profiles that are no longer in the database
        live = {(shas[a], shas[b], vshas[a], vshas[b]) for a, b in table}
        for key in [k for k in _PAIRS if k not in live]:
            del _PAIRS[key]
    return table


# ---------------------------------------------------------------- steps 2 and 3: profile, comparison, decision

def _database_fingerprints(profiles: Dict[str, dict], fingerprints: Optional[Dict[str, dict]]) -> Dict[str, dict]:
    fps = fingerprints if fingerprints is not None else dedup.load_fingerprints()
    return {k: v for k, v in fps.items() if k in profiles}


def compare(profile: Dict[str, Any], fingerprint: Optional[Dict[str, Any]], profiles: Dict[str, dict], tau: float,
            variants: Optional[Dict[str, List[dict]]] = None,
            fingerprints: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Compare a profile with the database (no LLM): duplicates of its capture, nearest cases, the campaigns it
    joins and the graded decision. `fingerprint` is dedup.fingerprint(case) or None (no duplicate check);
    `fingerprints` defaults to those of the cases on disk."""
    dups = dedup.find_duplicates(fingerprint, _database_fingerprints(profiles, fingerprints)) if fingerprint else []
    groups = clustering.cluster(profiles, tau, pair_table(profiles, variants))
    res = clustering.assign(profile, profiles, tau, groups=groups, variants=variants)
    return {"duplicates": dups, "neighbours": res["neighbours"], "joins": res["joins"],
            "decision": decision.decide(res["neighbours"], dups, likely=tau)}


def analyse(case: Dict[str, Any], profiles: Dict[str, dict], tau: float, client=None,
            variants: Optional[Dict[str, List[dict]]] = None,
            fingerprints: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Profile the case with the LLM and compare it. A repeat capture (same image or final URL as a database case)
    reuses that case's profile, so it costs no LLM call. Returns compare()'s keys plus "profile" and "llm_used"."""
    fps = _database_fingerprints(profiles, fingerprints)
    fp = dedup.fingerprint(case)
    repeat = next((d["case"] for d in dedup.find_duplicates(fp, fps)
                   if any(r.startswith(CAPTURE_REASONS) for r in d["reasons"])), None)
    if repeat:
        profile = profiles[repeat]
    else:
        from .llm.extract import extract
        profile = extract(case, client)
    return {"profile": profile, "llm_used": not repeat, **compare(profile, fp, profiles, tau, variants, fps)}


# ---------------------------------------------------------------- display and storage

def groups_overview(profiles: Dict[str, dict], tau: float, family_tau: float = decision.FAMILY_SCORE,
                    variants: Optional[Dict[str, List[dict]]] = None) -> List[Dict[str, Any]]:
    """Campaigns at tau, largest family first; each with its family number, members and the evidence that links them."""
    scores = pair_table(profiles, variants)
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
