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
# Every evidence label by kind; a strong_links entry is "<label>: <value>". clustering/evidence.py says which kinds
# join a campaign or a family, explain/catalog.py shows them.
LABELS = {
    "tracker": "shared tracker ID", "endpoint": "shared session/form endpoint",
    "file": "shared distinctive script/style file", "domain": "shared domain", "adid": "same ad campaign ID",
    "tracking": "same tracking template", "certificate": "domains on one certificate",
    "images": "shared page images", "page": "same sponsoring page",
}


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
    found = [
        ("tracker", min(common["tracker"]) if common["tracker"] else None),
        ("endpoint", min(common["endpoint"]) if len(common["endpoint"]) >= MIN_SHARED_ENDPOINTS else None),
        ("file", min(common["file"]) if common["file"] else None),
        ("domain", min(common["domain"]) if common["domain"] else None),
        ("adid", min((t[6:] for t in common["tracking"] if t.startswith("adid:")), default=None)),
        ("tracking", min((t[7:] for t in common["tracking"] if t.startswith("params:")), default=None)),
        ("certificate", min((fa["cert_san"] & fb["own_domains"]) | (fb["cert_san"] & fa["own_domains"]), default=None)),
        ("images", f"{len(common['images'])} identical image files" if len(common["images"]) >= MIN_SHARED_IMAGES else None),
        ("page", fa["page"] if fa["page"] and fa["page"] == fb["page"] else None),
    ]
    return [f"{LABELS[kind]}: {value}" for kind, value in found if value]


def kind_of(link: str) -> str:
    """The kind of one strong_links entry ("other" for an unknown label)."""
    return next((k for k, label in LABELS.items() if link.startswith(label + ":")), "other")
