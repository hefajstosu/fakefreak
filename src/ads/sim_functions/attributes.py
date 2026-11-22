"""Similarity of the attributes that need more than a generic measure (people, product, amounts, technical traces,
page fingerprints). Each takes the two raw values from the profiles and returns a float in [0, 1] or None."""
import re
from typing import List

from ..preprocess.domain_meta import linking_facts
from ..preprocess.page_fp import sketch_similarity
from ..urls import domains  # noqa: F401 (part of this module's API: domains of a URL list)
from .normalize import norm, parse_amount
from .primitives import Score, best_assignment, name_similarity, numeric_similarity, set_similarity

ROLE_ONLY_CREDIT = 0.5        # one side named, the other not, same role
SAME_ROLE_OTHER_PERSON = 0.3  # two different named people with the same role (a controlled swap)
PLACEHOLDER = "[product]"
SAME_CATEGORY_CREDIT = 0.5
OTHER_PRODUCT_SAME_CATEGORY = 0.3
# Parameter names that ad platforms and analytics add to every link: a set made only of these says nothing.
STANDARD_PARAMS = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "utm_id",
                             "fbclid", "gclid", "ttclid", "wbraid", "gbraid", "msclkid"})
AD_ID = re.compile(r"^\d{15,}$")


def person_pair(p: dict, q: dict) -> float:
    """Named people match by name; unnamed ones only by role, for less credit."""
    if p.get("name") and q.get("name"):
        s = name_similarity(p["name"], q["name"])
        if s >= 0.85:
            return s
        return SAME_ROLE_OTHER_PERSON if p.get("category_or_role") == q.get("category_or_role") else 0.0
    role_p, role_q = p.get("category_or_role"), q.get("category_or_role")
    if not (role_p and role_p == role_q):
        return 0.0
    return 1.0 if not p.get("name") and not q.get("name") else ROLE_ONLY_CREDIT


def featured_people(a, b) -> Score:
    return set_similarity(a, b, pair_sim=person_pair)


def product_or_platform(a, b) -> Score:
    """a, b = {"exact_name", "generic_category"}: same name 1.0; a missing or placeholder name (variants may use one)
    falls back to the category."""
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


def amount_pair(x: str, y: str) -> float:
    """Two amounts in the same unit by numeric closeness (PLN is never compared with % or a count)."""
    px, py = parse_amount(x), parse_amount(y)
    if px is None or py is None:
        return 1.0 if norm(x) == norm(y) and norm(x) else 0.0
    return numeric_similarity(px[0], py[0]) if px[1] == py[1] else 0.0


def amounts_dates_locations(a, b) -> Score:
    """Mean of the available parts: amounts (numeric, same unit), dates and locations (names)."""
    a, b = a or {}, b or {}
    parts = []
    xs, ys = [x for x in a.get("amounts", []) if x], [y for y in b.get("amounts", []) if y]
    if xs or ys:
        parts.append(best_assignment(xs, ys, amount_pair) / max(len(xs), len(ys)) if xs and ys else 0.0)
    parts += [s for s in (set_similarity(a.get(k, []), b.get(k, [])) for k in ("dates", "locations")) if s is not None]
    return sum(parts) / len(parts) if parts else None


def page_name(a, b) -> Score:
    """Sponsoring page name from the ad library metadata."""
    return name_similarity(a, b) if a and b else None


def page_structure(a, b) -> Score:
    """Best estimated Jaccard between any page of one case and any page of the other, from MinHash sketches of tag
    paths and CSS classes (preprocess/page_fp.py): a template keeps its skeleton when every word changes."""
    sa, sb = (a or {}).get("structure") or [], (b or {}).get("structure") or []
    if not sa or not sb:
        return None
    return max(sketch_similarity(u, v) for u in sa for v in sb)


# ---------------------------------------------------------------- tokens of the exact-match anchors

def url_tokens(urls) -> List[str]:
    """Tracking-template tokens of a case's URLs: `params:<sorted names>` when the query uses a name outside the
    platforms' standard set (the operator's own template), `adid:<id>` for a 15+ digit ad campaign ID."""
    out = set()
    for raw in urls or []:
        for u in raw.split(" -> "):
            q = u.split(" [")[0].strip().partition("?")[2]
            pairs = [kv.split("=", 1) + [""] for kv in q.split("&") if kv]
            names = sorted({kv[0] for kv in pairs if kv[0]})
            if names and set(names) - STANDARD_PARAMS:
                out.add("params:" + ",".join(names))
            out |= {"adid:" + v for k, v, *_ in pairs if k in ("utm_id", "utm_campaign") and AD_ID.match(v)}
    return sorted(out)


def tracking_tokens(technical: dict) -> List[str]:
    t = technical or {}
    return url_tokens((t.get("redirect_chain") or []) + (t.get("urls_and_domains") or []))


def infra_tokens(facts) -> List[str]:
    """Domain facts that can link two cases (preprocess/domain_meta.py): registration batch, non-mass name servers
    and hosting network, certificate neighbours. Registrar, country and dates describe but link nothing."""
    return linking_facts(facts or [])


def anchor_similarity(a, b, ignore: frozenset = frozenset()) -> Score:
    """Overlap |A ∩ B| / |A ∪ B| of exact-match traces, values in `ignore` (cluster.yaml: ignore_values) left out.
    None when either side has none: a page that could not be captured is missing data, not a mismatch."""
    sa = {x for x in a or [] if x and x not in ignore}
    sb = {x for x in b or [] if x and x not in ignore}
    if not sa or not sb:
        return None
    return len(sa & sb) / len(sa | sb)


