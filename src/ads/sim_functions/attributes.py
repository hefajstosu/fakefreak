"""One similarity function per profile attribute (schemas/profile.schema.json).

All take the two raw attribute values, return a float in [0, 1] or None ("no evidence"),
and never look at anything else, so they can be unit-tested one by one.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Optional
from urllib.parse import urlparse

from .normalize import norm, parse_amount
from .primitives import (Score, best_assignment, exact, jaccard, name_similarity,
                         numeric_similarity, set_similarity, text_similarity)

Embed = Optional[Callable]

# ---------------------------------------------------------------- enums: exact match

def scam_type(a, b) -> Score:
    return exact(a, b)


def topic(a, b) -> Score:
    return exact(a, b)


def ad_creative_template(a, b) -> Score:
    return exact(a, b)


def landing_page_template(a, b) -> Score:
    return exact(a, b)


def detected_language(a, b) -> Score:
    """A guard rather than a feature: if this is 0, text embeddings are not comparable."""
    return exact(a, b)


# ---------------------------------------------------------------- closed-vocabulary sets

def persuasion_devices(a, b) -> Score:
    return jaccard(a or [], b or [], both_empty=1.0)  # 'no devices' on both sides is agreement


def funnel_stages(a, b) -> Score:
    return jaccard(a or [], b or [], both_empty=1.0)


# ---------------------------------------------------------------- people

ROLE_ONLY_CREDIT = 0.5   # one side is named, the other is not, and the role matches
SAME_ROLE_OTHER_PERSON = 0.3  # two different named people with the same role (a controlled swap)


def _person_pair(p, q) -> float:
    if p.get("name") and q.get("name"):
        s = name_similarity(p["name"], q["name"])
        if s >= 0.85:
            return s
        return SAME_ROLE_OTHER_PERSON if p.get("category_or_role") == q.get("category_or_role") else 0.0
    role_p, role_q = p.get("category_or_role"), q.get("category_or_role")
    if not (role_p and role_p == role_q):
        return 0.0
    if not p.get("name") and not q.get("name"):
        return 1.0  # both unnamed, same role: indistinguishable (keeps sim(x, x) == 1)
    return ROLE_ONLY_CREDIT  # named on one side only


def featured_people(a, b) -> Score:
    """Named people match by (inflection-tolerant) name; unnamed ones only by role, for less credit."""
    return set_similarity(a or [], b or [], pair_sim=_person_pair)


# ---------------------------------------------------------------- name lists

def companies(a, b, soft: Optional[Callable] = None) -> Score:
    """`soft` lets a same-sector swap earn partial credit (see primitives.name_similarity)."""
    return set_similarity(a or [], b or [], pair_sim=lambda x, y: name_similarity(x, y, soft))


def impersonated_media(a, b, soft: Optional[Callable] = None) -> Score:
    return set_similarity(a or [], b or [], pair_sim=lambda x, y: name_similarity(x, y, soft))


def setting_and_props(a, b, soft: Optional[Callable] = None) -> Score:
    return set_similarity(a or [], b or [], pair_sim=lambda x, y: name_similarity(x, y, soft))


def keywords(a, b) -> Score:
    return set_similarity(a or [], b or [])


def logos_and_badges(a, b) -> Score:
    """Logos, channel bugs, LIVE banners, AI labels seen on the creative (the LLM lists them)."""
    return set_similarity(a or [], b or [])


# ---------------------------------------------------------------- product

PLACEHOLDER = "[product]"
SAME_CATEGORY_CREDIT = 0.5
OTHER_PRODUCT_SAME_CATEGORY = 0.3


def product_or_platform(a, b) -> Score:
    """a, b = {'exact_name', 'generic_category'}. Same name -> 1.0. The generator may replace the
    name with '[PRODUCT]' or the category, so a missing/placeholder name falls back to the category."""
    def name(p):
        n = norm((p or {}).get("exact_name"))
        return None if not n or n == norm(PLACEHOLDER) else n

    na, nb = name(a), name(b)
    ca, cb = norm((a or {}).get("generic_category")), norm((b or {}).get("generic_category"))
    if not (na or nb or ca or cb):
        return None
    if na and nb and name_similarity(na, nb) >= 0.85:
        return 1.0
    if ca and ca == cb:
        return OTHER_PRODUCT_SAME_CATEGORY if na and nb else SAME_CATEGORY_CREDIT
    return 0.0


# ---------------------------------------------------------------- amounts / dates / locations

def _amount_pair(x: str, y: str) -> float:
    px, py = parse_amount(x), parse_amount(y)
    if px is None or py is None:
        return 1.0 if norm(x) == norm(y) and norm(x) else 0.0
    if px[1] != py[1]:
        return 0.0  # never compare PLN with %, or a count
    return numeric_similarity(px[0], py[0])


def amounts_dates_locations(a, b) -> Score:
    """Mean of the available sub-scores: amounts (numeric closeness, same unit only),
    dates (soft set match) and locations (soft set match). Tip: the discount % ('-50%') is a more
    stable signal than absolute prices, which the generator is allowed to scale."""
    a, b = a or {}, b or {}
    parts = []
    xs, ys = [x for x in a.get("amounts", []) if x], [y for y in b.get("amounts", []) if y]
    if xs or ys:
        parts.append(0.0 if not (xs and ys) else best_assignment(xs, ys, _amount_pair) / max(len(xs), len(ys)))
    for key in ("dates", "locations"):
        s = set_similarity(a.get(key, []), b.get(key, []))
        if s is not None:
            parts.append(s)
    return sum(parts) / len(parts) if parts else None


# ---------------------------------------------------------------- free text (embeddings)

def narrative_pattern(a, b, embed: Embed = None) -> Score:
    return text_similarity(a, b, embed)


def promise_and_mechanism(a, b, embed: Embed = None) -> Score:
    return text_similarity(a, b, embed)


def call_to_action(a, b, embed: Embed = None) -> Score:
    return text_similarity(a, b, embed)


def canonical_comparison_text(a, b, embed: Embed = None) -> Score:
    return text_similarity(a, b, embed)


# ---------------------------------------------------------------- technical anchors

def domains(urls) -> list:
    """Hostnames of a list of URLs, lowercase; entries that are not URLs are ignored."""
    out = []
    for u in urls or []:
        host = urlparse(u if "://" in u else "//" + u).hostname
        if host and "." in host:
            out.append(host.lower())
    return out


def anchor_similarity(a, b, doc_freq: Optional[dict] = None, n_docs: Optional[int] = None,
                      ignore: frozenset = frozenset()) -> Score:
    """Rarity-weighted overlap of exact-match artifacts (tracker IDs, redirect domains, DOM/form clues).

    Each shared value counts log(N / df): a tracker seen in 2 of 10 cases is strong evidence, a CDN seen
    in all 10 is worth 0. Score = weight(shared) / weight(union). Without doc_freq all values weigh 1.
    `ignore` holds mass-infrastructure values (cluster.yaml: ignore_values) that are never evidence.
    None when either side has no values: like every other feature, data missing on one side is dropped, not scored 0.
    """
    sa = {x for x in (a or []) if x and x not in ignore}
    sb = {x for x in (b or []) if x and x not in ignore}
    if not sa or not sb:
        return None  # no traces on one side is missing data (page down, ad screenshot only), not a mismatch

    def w(v):
        if doc_freq and n_docs:
            return math.log(n_docs / max(1, doc_freq.get(v, 1)))
        return 1.0

    union = sum(w(v) for v in sa | sb)
    return sum(w(v) for v in sa & sb) / union if union > 0 else None


def ad_library_page_name(a, b) -> Score:
    """Advertiser page name from ad_library_metadata (usually null in the sample data)."""
    if not a or not b:
        return None
    return name_similarity(a, b)


# ---------------------------------------------------------------- tracking URL template

# Parameter names that ad platforms and analytics add to every link: a set made only of these says nothing.
STANDARD_PARAMS = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "utm_id",
                             "fbclid", "gclid", "ttclid", "wbraid", "gbraid", "msclkid"})
AD_ID = re.compile(r"^\d{15,}$")


def url_tokens(urls) -> list:
    """Tracking-template tokens of a case's URLs (redirect chain and landing URLs; har.sanitize_url keeps utm values):
    `params:<sorted names>` when the query uses a name outside the platforms' standard set (an operator's own
    template), `adid:<id>` for a 15+ digit ad or campaign ID in utm_id / utm_campaign (one ad platform campaign)."""
    out = set()
    for raw in urls or []:
        for u in raw.split(" -> "):
            q = urlparse(u.split(" [")[0].strip()).query
            if not q:
                continue
            pairs = [kv.split("=", 1) + [""] for kv in q.split("&") if kv]
            names = sorted({kv[0] for kv in pairs if kv[0]})
            if names and set(names) - STANDARD_PARAMS:
                out.add("params:" + ",".join(names))
            for k, v, *_ in pairs:
                if k in ("utm_id", "utm_campaign") and AD_ID.match(v):
                    out.add("adid:" + v)
    return sorted(out)


# ---------------------------------------------------------------- domain and infrastructure metadata

def infra_tokens(facts) -> list:
    """The facts of technical_artifacts.domain_and_cert_metadata that can link two cases (preprocess/domain_meta.py):
    registration batch, non-mass name servers and hosting network, certificate neighbours. Registrar, country and
    dates alone describe a domain but link nothing."""
    from ..preprocess.domain_meta import linking_facts
    return linking_facts(facts or [])


# ---------------------------------------------------------------- page fingerprints (preprocess/page_fp.py)

def page_structure(a, b) -> Score:
    """Best estimated Jaccard similarity between any page of one case and any page of the other, from MinHash
    sketches of tag paths and CSS class tokens: one landing-page template keeps its skeleton when every word changes.
    None when either side has no page (ad only, page not captured)."""
    sa, sb = (a or {}).get("structure") or [], (b or {}).get("structure") or []
    if not sa or not sb:
        return None
    return max(sum(x == y for x, y in zip(u, v)) / max(len(u), 1) for u in sa for v in sb)


# ---------------------------------------------------------------- non-grouping (diagnostics only)

def demographics_similarity(a, b) -> Score:
    """Fraction of equal descriptors per person_ref. NOT used in grouping (weight 0): useful only to
    check that demographics-only variants differ from the parent in exactly this attribute."""
    a, b = a or [], b or []
    if not a and not b:
        return None
    keys = ("skin_tone", "hair_color", "gender", "apparent_age_range")
    by_ref = {p.get("person_ref"): p for p in b}
    scores = []
    for p in a:
        q = by_ref.get(p.get("person_ref"))
        scores.append(0.0 if q is None else sum(p.get(k) == q.get(k) for k in keys) / len(keys))
    return sum(scores) / len(scores) if scores else 0.0
