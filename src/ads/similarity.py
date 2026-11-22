"""Placeholder similarity between two extracted profiles (to be replaced/improved by the similarity owner).

    from ads.similarity import score
    r = score(profile_a, profile_b)
    r == {"score": float in [0,1], "contributions": {feature: weighted contribution},
          "missing": [features skipped because one side had no data], "strong_links": [...]}

Everything else (clustering, evaluation, demo) calls only `score`, so the method can be swapped
without touching them. This baseline is a null-aware weighted average over structured features
plus a bag-of-words text similarity, with a rule that a shared tracker ID or session-endpoint
pattern is a strong link. No embeddings yet.
"""
import math
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlsplit

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CFG = yaml.safe_load(open(os.path.join(REPO, "config", "cluster.yaml"), encoding="utf-8"))
W = CFG["weights"]
STRONG = CFG["thresholds"]["strong_link"]
# Mass-infrastructure / boilerplate values that must never count as evidence.
GENERIC_FILES = {"main.js", "main.css", "style.css", "styles.css", "app.js", "script.js", "jquery.min.js",
                 "sw.js", "metrics.js", "email-decode.min.js", "utils.js", "slider.js", "video.js"}
STOP = set("the a an of and to in for on with is are was were be by as at it this that from or not".split())


def norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").casefold()).strip()


def jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def tokens(text: str) -> Counter:
    return Counter(t for t in re.findall(r"[\wąćęłńóśźż]+", norm(text)) if t not in STOP and len(t) > 2)


def cosine(a: Counter, b: Counter) -> float:
    num = sum(a[t] * b[t] for t in a.keys() & b.keys())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def reg_domain(url: str) -> str:
    h = (urlsplit(url if "//" in url else "//" + url).hostname or "").lower()
    p = h.split(".")
    return ".".join(p[-3:] if ".".join(p[-2:]) in ("com.pl", "org.pl", "net.pl") else p[-2:])


def _set(items) -> Set[str]:
    return {norm(x) for x in items if x}


def features(p: Dict[str, Any]) -> Dict[str, Any]:
    n, e, v = p["core_narrative"], p["entities"], p["visual_and_production"]
    ta = p["technical_artifacts"]
    clues = ta.get("dom_and_form_clues", [])
    # observed POSTs (from HAR) and endpoint paths written in page scripts ("api:" clues from the URL scan) are
    # reduced to the same host-independent prefix, e.g. "POST */api/v1/trigger/field/"
    endpoints = {re.sub(r" fields=.*", "", c) for c in clues if c.startswith("POST ")}
    endpoints = {re.sub(r"^POST [^/]+", "POST *", c) for c in endpoints}
    endpoints |= {"POST *" + c[4:] for c in clues if c.startswith("api:")}
    endpoints = {re.sub(r"/<uuid>.*$", "/", c) for c in endpoints}
    files = {c[5:] for c in clues if c.startswith("file:") and c[5:].lower() not in GENERIC_FILES}
    return {
        "scam_type": n["ad_goal_scam_type"], "topic": n["topic"],
        "ad_creative_template": v["ad_creative_template"], "landing_page_template": v["landing_page_template"],
        "persuasion_devices": _set(n["persuasion_devices"]),
        "product_name": norm(e["product_or_platform"]["exact_name"]) or None,
        "featured_people": _set(x["name"] for x in e["featured_people"] if x["name"]),
        "companies": _set(e["companies_or_institutions"]), "impersonated_media": _set(e["impersonated_media"]),
        "text": tokens(" ".join([p["canonical_comparison_text"], n["narrative_pattern"], n["promise_and_mechanism"]])),
        "call_to_action": tokens(n["call_to_action"]),
        "setting_and_props": set(t for x in v["setting_and_props"] for t in tokens(x)),
        "amounts_dates_locations": set(re.findall(r"\d[\d ]*", " ".join(e["amounts_dates_locations"]["amounts"]))),
        "_trackers": set(ta.get("tracker_ids", [])),
        "_domains": {reg_domain(u) for u in ta.get("redirect_chain", []) + ta.get("urls_and_domains", []) if u},
        "_endpoints": endpoints, "_files": files,
        "_page": norm(ta["ad_library_metadata"]["page_id_or_name"]) or None,
    }


def _pair(name: str, a: Any, b: Any):
    """Return similarity in [0,1] or None when the feature cannot be compared."""
    if name in ("scam_type", "topic", "ad_creative_template", "landing_page_template", "product_name"):
        if not a or not b or "other" in (a, b) and name != "product_name":
            return None
        return 1.0 if a == b else 0.0
    if name in ("text", "call_to_action"):
        return cosine(a, b) if a and b else None
    if isinstance(a, set):
        return jaccard(a, b) if (a and b) else None
    return None


def score(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    fa, fb = features(a), features(b)
    contributions: Dict[str, float] = {}
    missing: List[str] = []
    num = den = 0.0
    for name, w in (("scam_type", W["scam_type"]), ("topic", W["scam_type"] * 0.5),
                    ("ad_creative_template", W["ad_creative_template"]),
                    ("landing_page_template", W["landing_page_template"]),
                    ("persuasion_devices", W["persuasion_devices"]), ("product_name", W["product_name"]),
                    ("featured_people", W["featured_people"]), ("companies", W["companies"]),
                    ("impersonated_media", W["impersonated_media"]), ("text", W["embedding"]),
                    ("call_to_action", W["call_to_action"]), ("setting_and_props", W["setting_and_props"]),
                    ("amounts_dates_locations", W["amounts_dates_locations"])):
        s = _pair(name, fa[name], fb[name])
        if s is None:
            missing.append(name)
            continue
        num += w * s
        den += w
        contributions[name] = round(w * s, 4)
    base = num / den if den else 0.0
    strong: List[str] = []
    for key, label, kind in (("_trackers", "shared tracker ID", "tracker"), ("_endpoints", "shared session/form endpoint", "endpoint"),
                             ("_files", "shared distinctive script/style file", "file"),
                             ("_domains", "shared domain", "domain")):
        common = fa[key] & fb[key]
        if kind == "endpoint" and len(common) < 2:
            continue  # one shared generic path (e.g. /api/v1/) is too weak; a platform shares several
        if common and kind != "file":
            strong.append(f"{label}: {sorted(common)[0]}")
        elif common and kind == "file":
            strong.append(f"{label}: {sorted(common)[0]}")
    if fa["_page"] and fa["_page"] == fb["_page"]:
        strong.append(f"same sponsoring page: {fa['_page']}")
    # tracker IDs and shared domains are near-conclusive; endpoints/files/pages are supporting evidence
    final = base
    if any(s.startswith(("shared tracker", "shared domain", "same sponsoring")) for s in strong):
        final = max(final, STRONG)
    elif any(s.startswith(("shared session", "shared distinctive")) for s in strong):
        final = min(1.0, base + 0.15)
    return {"score": round(final, 4), "base": round(base, 4), "contributions": contributions,
            "missing": missing, "strong_links": strong}
