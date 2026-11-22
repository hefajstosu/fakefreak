"""Analyse new material against the database, with no UI code. The web panel and the Streamlit demo both use it.

Three steps, each usable on its own:

    case, notes = build_case(url="https://...", text="", images=[], html_files=[])   # material -> case_input
    result = analyse(case, profiles, tau, client)    # duplicate check, LLM profile (skipped for a repeat), compare
    result = compare(profile, fingerprint, profiles, tau)   # duplicates, nearest cases, campaigns joined, decision

and for display and storage:

    groups = groups_overview(profiles, tau)          # campaigns with their family, members and linking evidence
    scores = pair_table(profiles)                    # the N x N pair table, reused between calls (see its docstring)
    groups = campaigns(profiles, tau)                # campaigns at tau, reused while the database is unchanged
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

from . import clustering, decision, dedup, explain
from .paths import CASES, DATA
from .preprocess.har import host, reg_domain

EMPTY_TECH = {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [], "dom_and_form_clues": [],
              "domain_and_cert_metadata": []}
CAPTURE_REASONS = ("near-identical image", "same final URL")  # the same capture again (see decision.py)


# ---------------------------------------------------------------- step 1: material -> case_input

UPLOAD_KINDS = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
                ".html": "html", ".htm": "html", ".har": "har", ".txt": "text",
                ".mp4": "video", ".mov": "video", ".webm": "video", ".m4v": "video"}
MAX_CREATIVES = 6  # screenshots sent to the LLM as the ad creative; more would cost tokens without new information


def classify_files(paths: Sequence[str]) -> Dict[str, List[str]]:
    """Uploaded files by kind (image, html, har, text, video, unsupported), from their extension."""
    out: Dict[str, List[str]] = {}
    for p in paths:
        out.setdefault(UPLOAD_KINDS.get(os.path.splitext(p)[1].lower(), "unsupported"), []).append(p)
    return out


def build_case(url: str = "", text: str = "", images: Sequence[str] = (), html_files: Sequence[str] = (),
               product: str = "", text_role: str = "bridge_page", domain_meta: bool = True,
               hars: Sequence[str] = (), videos: Sequence[str] = (), text_files: Sequence[str] = (),
               work_dir: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """In-memory case_input from what an analyst has: a URL (scanned for text and technical traces), pasted text,
    screenshots, saved HTML pages, HAR network logs, videos, text files and a product name. Returns (None, notes)
    when nothing usable is given. With `domain_meta` the domains found get public registration, hosting and
    certificate facts.

    Screenshots (at most MAX_CREATIVES) and video contact sheets become the ad creative, each HTML or text file a bridge
    page, and the scanned plus pasted text one more page with role `text_role` (default: a bridge page, i.e. the fake
    article). HAR logs give the technical traces (preprocess/har.py) and, with the pages, the page fingerprints.
    Video contact sheets are written to `work_dir`."""
    from .preprocess import page_fp
    notes: List[str] = []
    tech: Dict[str, Any] = {k: list(v) for k, v in EMPTY_TECH.items()}
    fps = []
    page_text = text.strip()
    if url.strip():
        from .preprocess.url_scan import scan_url
        scan = scan_url(url.strip())
        if scan["ok"]:
            page_text = "\n".join(t for t in (scan["text"], page_text) if t)
            fps.append(scan["technical_summary"].pop("page_fingerprints", {}))
            tech = scan["technical_summary"]
            notes += scan["notes"]
            if scan["final_url"].rstrip("/") != url.strip().rstrip("/"):
                notes.append(f"redirected to {scan['final_url']}")
        else:
            notes.append(f"could not fetch the page: {scan['error']}")
    if hars:
        from .preprocess import har as harmod
        for h in hars:
            try:
                harmod.process(h, tech)
                fps.append(page_fp.from_har(h))
            except (ValueError, KeyError, OSError) as e:
                notes.append(f"could not read the network log {os.path.basename(h)}: {str(e)[:80]}")
    if domain_meta and (tech["urls_and_domains"] or tech["redirect_chain"]):
        try:  # public registries only (RDAP, DNS, certificate logs, archive); failures leave it out
            from .preprocess import domain_meta as dm
            captured = dm.capture_date({"hars": list(hars)}, "") if hars else dm.today()
            tech["domain_and_cert_metadata"] = dm.case_metadata(tech, captured=captured or dm.today())
        except Exception as e:  # noqa: BLE001
            notes.append(f"domain metadata unavailable: {str(e)[:80]}")
    if product.strip():
        page_text = f"Product or platform named by the analyst: {product.strip()}\n" + page_text
    creatives = list(images)
    if len(creatives) > MAX_CREATIVES:
        notes.append(f"{len(creatives)} images given: the first {MAX_CREATIVES} are analysed as the ad creative")
        creatives = creatives[:MAX_CREATIVES]
    for v in videos:
        try:
            from .preprocess import video as videomod
            samples, _ = videomod.sample_frames(v, 48, 0.0, 0.0, None)
            sheet = os.path.join(work_dir or os.path.dirname(v), os.path.splitext(os.path.basename(v))[0] + "_sheet.jpg")
            videomod.make_contact_sheet(videomod.pick_keyframes(samples), sheet)
            creatives.append(sheet)
        except Exception as e:  # noqa: BLE001
            notes.append(f"could not read the video {os.path.basename(v)}: {str(e)[:80]}")
    parts: List[Dict[str, Any]] = []
    if creatives:
        parts.append({"role": "ad_creative", "medium": "image", "text": None, "images": creatives})
    if html_files:
        from .preprocess.assemble import html_to_text
        parts += [{"role": "bridge_page", "medium": "html", "text": html_to_text(p), "images": []} for p in html_files]
        fps += [page_fp.from_saved_page(p) for p in html_files]
    for t in text_files:
        body = open(t, encoding="utf-8", errors="ignore").read().strip()
        if body:
            parts.append({"role": "bridge_page", "medium": "text", "text": body[:40000], "images": []})
    if hars and not html_files and not text_files and not url.strip():  # a log alone: read its pages
        for h in hars:
            try:
                parts += [{"role": "bridge_page", "medium": "text", "text": t, "images": []}
                          for t in page_fp.har_page_texts(h)[:3]]
            except (ValueError, KeyError, OSError):
                pass
    if page_text.strip():
        parts.append({"role": text_role, "medium": "text", "text": page_text.strip(), "images": []})
    if not parts:
        if hars:
            notes.append("the network logs hold no readable page: add the article text, a screenshot or the saved page")
        return None, notes
    merged = page_fp.merge(*fps)
    if merged["structure"] or merged["images"]:
        tech["page_fingerprints"] = merged
    return {"schema_version": "1.0", "case_id": "new", "parts": parts, "technical_summary": tech,
            "resolved_identities": []}, notes


# ---------------------------------------------------------------- the pair table, reused between analyses

_PAIRS: Dict[Tuple[str, ...], Dict[str, Any]] = {}  # (sha a, sha b, variants sha a, variants sha b) -> pair result
_GROUPS: Dict[Tuple[Any, ...], List[List[str]]] = {}  # (tau, database content) -> campaigns
_SHAS: Dict[int, Tuple[dict, str]] = {}               # id(profile) -> (profile, sha), for the current database


def _sha(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _content_keys(profiles: Dict[str, dict], variants: Dict[str, List[dict]]) -> Dict[str, Tuple[str, str]]:
    """{case id: (profile sha, variants sha)}. Profiles are never edited in place, so a profile object already
    hashed in the previous call is not hashed again; only the current database is remembered."""
    global _SHAS
    seen = {}
    for p in profiles.values():
        old = _SHAS.get(id(p))
        seen[id(p)] = old if old is not None and old[0] is p else (p, _sha(p))
    _SHAS = seen
    return {c: (seen[id(p)][1], _sha(variants[c]) if variants.get(c) else "") for c, p in profiles.items()}


def pair_table(profiles: Dict[str, dict],
               variants: Optional[Dict[str, List[dict]]] = None) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """clustering.pair_scores(profiles, variants), with every pair remembered by the content of its two profiles
    (and their variants). A long-running panel therefore compares a pair once: after a case is saved the next
    analysis costs N new comparisons instead of N*(N-1)/2. Results keep only "score", "base", "via_variant" and
    "strong_links", which is all the grouping reads. The memory holds about twice the current table at most."""
    variants = variants or {}
    keys = _content_keys(profiles, variants)
    table = {}
    for a, b in combinations(sorted(profiles), 2):
        key = keys[a] + keys[b]
        if key not in _PAIRS:
            r = clustering.best_score(profiles[a], profiles[b], variants.get(a), variants.get(b))
            _PAIRS[key] = {k: r[k] for k in ("score", "base", "via_variant", "strong_links")}
        table[(a, b)] = _PAIRS[key]
    if len(_PAIRS) > 2 * len(table) + 1000:  # drop pairs of profiles that are no longer in the database
        live = {keys[a] + keys[b] for a, b in table}
        for key in [k for k in _PAIRS if k not in live]:
            del _PAIRS[key]
    return table


def campaigns(profiles: Dict[str, dict], tau: float,
              variants: Optional[Dict[str, List[dict]]] = None) -> List[List[str]]:
    """clustering.cluster(profiles, tau) over pair_table(), remembered while the database and tau stay the same:
    analysing several articles in a row clusters the database once, and again only after a case is saved."""
    keys = _content_keys(profiles, variants or {})
    key = (tau, tuple(sorted((c,) + k for c, k in keys.items())))
    if key not in _GROUPS:
        if len(_GROUPS) >= 16:
            _GROUPS.clear()
        _GROUPS[key] = clustering.cluster(profiles, tau, pair_table(profiles, variants))
    return [list(g) for g in _GROUPS[key]]


def families(profiles: Dict[str, dict], tau: float,
             variants: Optional[Dict[str, List[dict]]] = None) -> List[List[str]]:
    """Families of campaigns (clustering.hierarchy at decision.FAMILY_SCORE) as member lists, remembered like
    campaigns()."""
    keys = _content_keys(profiles, variants or {})
    key = ("families", tau, tuple(sorted((c,) + k for c, k in keys.items())))
    if key not in _GROUPS:
        groups = campaigns(profiles, tau, variants)
        fams = clustering.hierarchy(profiles, groups, decision.FAMILY_SCORE, pair_table(profiles, variants))
        _GROUPS[key] = [sorted(c for i in f for c in groups[i]) for f in fams]
    return [list(f) for f in _GROUPS[key]]


# ---------------------------------------------------------------- steps 2 and 3: profile, comparison, decision

def _database_fingerprints(profiles: Dict[str, dict], fingerprints: Optional[Dict[str, dict]]) -> Dict[str, dict]:
    fps = fingerprints if fingerprints is not None else dedup.load_fingerprints()
    return {k: v for k, v in fps.items() if k in profiles}


def compare(profile: Dict[str, Any], fingerprint: Optional[Dict[str, Any]], profiles: Dict[str, dict], tau: float,
            variants: Optional[Dict[str, List[dict]]] = None,
            fingerprints: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Compare a profile with the database (no LLM): duplicates of its capture, nearest cases, the campaigns it
    joins and the graded decision, plus why: "reasons" (the decision rule and its numbers), "campaigns" (per
    campaign, joined or not and on which rule) and "families" / "family_joins" (the families of campaigns it
    belongs to: same scam type and a score >= decision.FAMILY_SCORE or shared platform endpoints; see explain.py). `fingerprint` is dedup.fingerprint(case) or None (no duplicate check);
    `fingerprints` defaults to those of the cases on disk."""
    dups = dedup.find_duplicates(fingerprint, _database_fingerprints(profiles, fingerprints)) if fingerprint else []
    res = clustering.assign(profile, profiles, tau, groups=campaigns(profiles, tau, variants), variants=variants)
    hard = [(c, r) for c, r in res["scores"].items() if clustering.is_must_link(r)]
    fam = explain.family_assignment(profile, res["scores"], families(profiles, tau, variants), profiles)
    fam_links = [(c, res["scores"][c]) for row in fam for c in row["evidence_with"]]
    dec = decision.decide(res["neighbours"], dups, likely=tau, hard=hard, family_links=fam_links)
    return {"duplicates": dups, "neighbours": res["neighbours"], "joins": res["joins"], "decision": dec,
            "reasons": explain.decision_reasons(dec, res["neighbours"], tau),
            "campaigns": explain.assignment(res, tau), "families": fam,
            "family_joins": [row["members"] for row in fam if row["joined"]]}


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
    """Campaigns at tau, largest family first; each with its family number, members, the evidence that links them
    and its explanation (explain.campaign: signature, cohesion, hard links, nearest other campaign)."""
    scores = pair_table(profiles, variants)
    groups = campaigns(profiles, tau, variants)
    out = []
    for fam_no, family in enumerate(clustering.hierarchy(profiles, groups, family_tau, scores), 1):
        for ci in family:
            members = groups[ci]
            links = [{"a": a, "b": b, "score": clustering.pair(scores, a, b)["score"],
                      "evidence": clustering.pair(scores, a, b)["strong_links"]} for a, b in combinations(members, 2)]
            scam = Counter(profiles[c]["core_narrative"]["ad_goal_scam_type"] for c in members).most_common(1)[0][0]
            out.append({"family": fam_no, "members": members, "scam_type": scam,
                        "links": sorted(links, key=lambda x: -x["score"]),
                        "explanation": explain.campaign(members, profiles, scores, tau, groups)})
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
        "infra": [f for f in ta.get("domain_and_cert_metadata") or [] if not f.startswith(("domain:", "regbatch:"))],
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
