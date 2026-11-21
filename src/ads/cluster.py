"""Placeholder grouping: single-link clusters at a threshold over `similarity.score`.

    groups = cluster(profiles, tau)      # profiles: {case_id: profile}; returns list of sorted id lists
    assign(new_profile, profiles, tau)   # which existing groups a new profile joins (several allowed), else new group

To be replaced by the calibrated, hierarchical version (per-campaign thresholds, 'unconfirmed'
status, family edges). Same interface is enough for the demo and the evaluation.
"""
from itertools import combinations
from typing import Any, Dict, List

from .similarity import score


def pair_scores(profiles: Dict[str, Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
    return {(a, b): score(profiles[a], profiles[b]) for a, b in combinations(sorted(profiles), 2)}


def cluster(profiles: Dict[str, Dict[str, Any]], tau: float, scores: Dict[tuple, Dict[str, Any]] = None) -> List[List[str]]:
    scores = scores or pair_scores(profiles)
    parent = {k: k for k in profiles}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), r in scores.items():
        if r["score"] >= tau:
            parent[find(a)] = find(b)
    groups: Dict[str, List[str]] = {}
    for k in profiles:
        groups.setdefault(find(k), []).append(k)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g))


def assign(new: Dict[str, Any], profiles: Dict[str, Dict[str, Any]], tau: float, top: int = 5) -> Dict[str, Any]:
    """Rank existing profiles by similarity to `new` and say which groups it joins (or that it is new)."""
    ranked = sorted(((cid, score(new, p)) for cid, p in profiles.items()), key=lambda x: -x[1]["score"])
    groups = cluster(profiles, tau)
    joined = [g for g in groups if any(r["score"] >= tau for cid, r in ranked if cid in g)]
    return {"neighbours": ranked[:top], "joins": joined, "is_new_group": not joined}
