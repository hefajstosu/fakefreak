"""The database as the panel queries it: the N x N pair table, campaigns and families, remembered between analyses.

A long-running panel compares each pair of profiles once (by content), clusters the database once per threshold and
again only after a case is saved. The memory holds about the current table; reset() empties it.
"""
import hashlib
import json
from itertools import combinations
from typing import Any, Dict, List, Tuple

from .. import clustering, decision
from ..similarity import score

_PAIRS: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (sha a, sha b) -> pair result
_GROUPS: Dict[Tuple[Any, ...], List[List[str]]] = {}  # (level, tau, database content) -> member lists
_SHAS: Dict[int, Tuple[dict, str]] = {}               # id(profile) -> (profile, sha), for the current database


def reset() -> None:
    _PAIRS.clear()
    _GROUPS.clear()
    _SHAS.clear()


def _sha(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _content(profiles: Dict[str, dict]) -> Dict[str, str]:
    """{case id: profile sha}. Profiles are never edited in place, so an object hashed in the previous call is not
    hashed again; only the current database is remembered."""
    global _SHAS
    seen = {}
    for p in profiles.values():
        old = _SHAS.get(id(p))
        seen[id(p)] = old if old is not None and old[0] is p else (p, _sha(p))
    _SHAS = seen
    return {c: seen[id(p)][1] for c, p in profiles.items()}


def pair_table(profiles: Dict[str, dict]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """clustering.pair_scores(profiles), each pair remembered by the content of its two profiles: after a case is
    saved the next analysis scores N new pairs instead of N*(N-1)/2. Keeps "score" and "strong_links" only, which is
    all grouping reads."""
    keys = _content(profiles)
    table = {}
    for a, b in combinations(sorted(profiles), 2):
        key = (keys[a], keys[b])
        if key not in _PAIRS:
            r = score(profiles[a], profiles[b])
            _PAIRS[key] = {"score": r["score"], "strong_links": r["strong_links"]}
        table[(a, b)] = _PAIRS[key]
    if len(_PAIRS) > 2 * len(table) + 1000:  # forget pairs of profiles that left the database
        live = {(keys[a], keys[b]) for a, b in table}
        for key in [k for k in _PAIRS if k not in live]:
            del _PAIRS[key]
    return table


def _remembered(level: str, profiles: Dict[str, dict], tau: float, build) -> List[List[str]]:
    key = (level, tau, tuple(sorted(_content(profiles).items())))
    if key not in _GROUPS:
        if len(_GROUPS) >= 16:
            _GROUPS.clear()
        _GROUPS[key] = build()
    return [list(g) for g in _GROUPS[key]]


def campaigns(profiles: Dict[str, dict], tau: float) -> List[List[str]]:
    """clustering.cluster over pair_table(), remembered while the database and tau stay the same."""
    return _remembered("campaigns", profiles, tau, lambda: clustering.cluster(profiles, tau, pair_table(profiles)))


def families(profiles: Dict[str, dict], tau: float) -> List[List[str]]:
    """Families of campaigns (clustering.hierarchy at decision.FAMILY_SCORE) as member lists, remembered alike."""
    def build():
        groups = campaigns(profiles, tau)
        fams = clustering.hierarchy(profiles, groups, decision.FAMILY_SCORE, pair_table(profiles))
        return [sorted(c for i in f for c in groups[i]) for f in fams]
    return _remembered("families", profiles, tau, build)
