"""Human-readable hard evidence (shared tracker, endpoint, file, domain, sponsoring page) for a pair of profiles.

Reporting only: these links are shown in the demo and used by decision.py. The number comes from
`compare_all`; evidence never changes it.
"""
from __future__ import annotations

import re
from typing import List

from . import attributes as A
from .aggregate import get
from .normalize import norm

# Mass-infrastructure / boilerplate files that must never count as evidence.
GENERIC_FILES = {"main.js", "main.css", "style.css", "styles.css", "app.js", "script.js", "jquery.min.js",
                 "sw.js", "metrics.js", "email-decode.min.js", "utils.js", "slider.js", "video.js"}
MIN_SHARED_ENDPOINTS = 2  # one shared generic path (e.g. /api/v1/) is too weak; a platform shares several


def _reg_domain(host: str) -> str:
    p = host.split(".")
    return ".".join(p[-3:] if ".".join(p[-2:]) in ("com.pl", "org.pl", "net.pl") else p[-2:])


def _endpoints(clues) -> set:
    # observed POSTs (HAR) and "api:" paths from the URL scan reduce to one host-independent prefix
    out = {re.sub(r"^POST [^/]+", "POST *", re.sub(r" fields=.*", "", c)) for c in clues if c.startswith("POST ")}
    out |= {"POST *" + c[4:] for c in clues if c.startswith("api:")}
    return {re.sub(r"/<uuid>.*$", "/", c) for c in out}


def _anchors(p: dict) -> dict:
    ta = p.get("technical_artifacts") or {}
    clues = ta.get("dom_and_form_clues") or []
    return {
        "tracker": set(ta.get("tracker_ids") or []),
        "endpoint": _endpoints(clues),
        "file": {c[5:] for c in clues if c.startswith("file:") and c[5:].lower() not in GENERIC_FILES},
        "domain": {_reg_domain(h) for h in A.domains((ta.get("redirect_chain") or []) + (ta.get("urls_and_domains") or []))},
        "page": norm(get(ta, "ad_library_metadata.page_id_or_name")) or None,
    }


def strong_links(a: dict, b: dict) -> List[str]:
    fa, fb = _anchors(a), _anchors(b)
    out: List[str] = []
    for kind, label in (("tracker", "shared tracker ID"), ("endpoint", "shared session/form endpoint"),
                        ("file", "shared distinctive script/style file"), ("domain", "shared domain")):
        common = fa[kind] & fb[kind]
        if kind == "endpoint" and len(common) < MIN_SHARED_ENDPOINTS:
            continue
        if common:
            out.append(f"{label}: {sorted(common)[0]}")
    if fa["page"] and fa["page"] == fb["page"]:
        out.append(f"same sponsoring page: {fa['page']}")
    return out
