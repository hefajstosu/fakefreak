"""Group the database cases by one trait: every distinct value of the trait becomes a group of the cases that have it.

Unlike campaigns (similarity.py / clustering) this is a plain lookup: no scores, no threshold. A case with several values
for a list trait (people, domains, trackers...) appears in each of their groups; a case with no value goes to "no value".
Values are compared case-insensitively ("TVN24" and "tvn24" are one group); the first spelling seen is shown.
"""
from typing import Any, Callable, Dict, List, Tuple

from .. import analysis

NO_VALUE = ""  # group key of the cases that have no value for the trait


def _one(x) -> List[str]:
    return [x] if x else []


# trait key -> (label shown in the panel, function (profile, case summary) -> list of values)
TRAITS: Dict[str, Tuple[str, Callable[[dict, dict], List[str]]]] = {
    "scam_type": ("Typ oszustwa", lambda p, s: _one(p["core_narrative"]["ad_goal_scam_type"])),
    "topic": ("Temat", lambda p, s: _one(p["core_narrative"]["topic"])),
    "product": ("Produkt / platforma", lambda p, s: _one(s["product"])),
    "people": ("Osoby", lambda p, s: s["people"]),
    "media": ("Podszywane media", lambda p, s: s["media"] or []),
    "companies": ("Firmy i instytucje", lambda p, s: s["companies"] or []),
    "ad_template": ("Szablon reklamy", lambda p, s: _one(p["visual_and_production"]["ad_creative_template"])),
    "landing_template": ("Szablon strony docelowej", lambda p, s: _one(p["visual_and_production"]["landing_page_template"])),
    "persuasion": ("Techniki perswazji", lambda p, s: s["persuasion"]),
    "domains": ("Domeny", lambda p, s: s["domains"]),
    "trackers": ("Identyfikatory trackerów", lambda p, s: s["trackers"]),
}


def trait_list() -> List[Dict[str, str]]:
    return [{"key": k, "label": label} for k, (label, _) in TRAITS.items()]


def group_by(profiles: Dict[str, dict], trait: str) -> List[Dict[str, Any]]:
    """Groups of case ids per value of `trait`, biggest first (the no-value group last), ties by value."""
    if trait not in TRAITS:
        raise ValueError(f"unknown trait: {trait}")
    extract = TRAITS[trait][1]
    shown: Dict[str, str] = {}
    members: Dict[str, List[str]] = {}
    for cid in sorted(profiles):
        p = profiles[cid]
        values = [str(v).strip() for v in extract(p, analysis.case_summary(cid, p))]
        keys = []
        for v in values:
            k = v.casefold()
            if k and k not in keys:
                keys.append(k)
                shown.setdefault(k, v)
        for k in keys or [NO_VALUE]:
            members.setdefault(k, []).append(cid)
    order = sorted(members, key=lambda k: (k == NO_VALUE, -len(members[k]), k))
    return [{"value": shown.get(k), "members": members[k]} for k in order]
