"""Shared traces of two profiles stated in words: what links them beyond a similar score.

Reporting only: the score comes from features.compare_all and evidence never changes it. Grouping reads the labels:
clustering/evidence.py says which ones join a campaign (must-link) and which a family of campaigns.
"""
import re
from typing import List

from ..urls import domains, reg_domain
from .attributes import tracking_tokens
from .features import get
from .normalize import norm

# Boilerplate file names that never count as evidence.
GENERIC_FILES = {"main.js", "main.css", "style.css", "styles.css", "app.js", "script.js", "jquery.min.js",
                 "sw.js", "metrics.js", "email-decode.min.js", "utils.js", "slider.js", "video.js"}
MIN_SHARED_ENDPOINTS = 2  # one shared generic path (/api/v1/) is too weak; a platform shares several
MIN_SHARED_IMAGES = 2     # one shared picture can be a stock photo; an operator's page kit shares several


def _endpoints(clues) -> set:
    """Recorded POSTs (HAR) and api: paths (live scan) reduced to one host-independent prefix."""
    out = {re.sub(r"^POST [^/]+", "POST *", re.sub(r" fields=.*", "", c)) for c in clues if c.startswith("POST ")}
    out |= {"POST *" + c[4:] for c in clues if c.startswith("api:")}
    return {re.sub(r"/<uuid>.*$", "/", c) for c in out}


def _traces(p: dict) -> dict:
    ta = p.get("technical_artifacts") or {}
    clues = ta.get("dom_and_form_clues") or []
    facts = ta.get("domain_and_cert_metadata") or []
    return {
        "tracker": set(ta.get("tracker_ids") or []),
        "endpoint": _endpoints(clues),
        "file": {c[5:] for c in clues if c.startswith("file:") and c[5:].lower() not in GENERIC_FILES},
        "domain": {reg_domain(h) for h in domains((ta.get("redirect_chain") or []) + (ta.get("urls_and_domains") or []))},
        "tracking": set(tracking_tokens(ta)),
        "images": set(get(ta, "page_fingerprints.images") or []),
        "cert_san": {f[9:] for f in facts if f.startswith("cert_san:")},
        "own_domains": {f[7:] for f in facts if f.startswith("domain:")},
        "page": norm(get(ta, "ad_library_metadata.page_id_or_name")) or None,
    }


def strong_links(a: dict, b: dict) -> List[str]:
    fa, fb = _traces(a), _traces(b)
    common = {k: fa[k] & fb[k] for k in ("tracker", "endpoint", "file", "domain", "tracking", "images")}
    out = []
    if common["tracker"]:
        out.append(f"shared tracker ID: {min(common['tracker'])}")
    if len(common["endpoint"]) >= MIN_SHARED_ENDPOINTS:
        out.append(f"shared session/form endpoint: {min(common['endpoint'])}")
    if common["file"]:
        out.append(f"shared distinctive script/style file: {min(common['file'])}")
    if common["domain"]:
        out.append(f"shared domain: {min(common['domain'])}")
    ad_ids = sorted(t[6:] for t in common["tracking"] if t.startswith("adid:"))
    if ad_ids:
        out.append(f"same ad campaign ID: {ad_ids[0]}")
    templates = sorted(t[7:] for t in common["tracking"] if t.startswith("params:"))
    if templates:
        out.append(f"same tracking template: {templates[0]}")
    on_cert = (fa["cert_san"] & fb["own_domains"]) | (fb["cert_san"] & fa["own_domains"])
    if on_cert:
        out.append(f"domains on one certificate: {min(on_cert)}")
    if len(common["images"]) >= MIN_SHARED_IMAGES:
        out.append(f"shared page images: {len(common['images'])} identical image files")
    if fa["page"] and fa["page"] == fb["page"]:
        out.append(f"same sponsoring page: {fa['page']}")
    return out
