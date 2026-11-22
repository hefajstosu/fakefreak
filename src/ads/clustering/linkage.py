"""Average-link agglomerative clustering over a pair-score table, with must-link seeds.

Average link merges two groups only when the MEAN score between their members reaches tau, so one weak
bridge between two campaigns cannot chain them together (single link does). Must-link pairs (hard evidence)
are merged first and unconditionally. Pure Python; fine for the hundreds of articles this project handles.
"""
from typing import Dict, List, Optional, Tuple

from .evidence import is_must_link
from .pairs import Profiles, Scores, Variants, pair, pair_scores


def _components(ids: List[str], edges: List[Tuple[str, str]]) -> List[List[str]]:
    parent = {k: k for k in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: Dict[str, List[str]] = {}
    for k in ids:
        groups.setdefault(find(k), []).append(k)
    return list(groups.values())


def average_score(g1: List[str], g2: List[str], scores: Scores) -> float:
    return sum(pair(scores, a, b)["score"] for a in g1 for b in g2) / (len(g1) * len(g2))


def cluster(profiles: Profiles, tau: float, scores: Optional[Scores] = None, use_must_link: bool = True,
            variants: Optional[Variants] = None, variant_gate: Optional[float] = None) -> List[List[str]]:
    """Campaign groups: sorted id lists, largest first. Only keys of `profiles` are ever grouped; `variants`
    (used only when `scores` is not given) help the real articles score higher but never appear in a group."""
    scores = scores if scores is not None else pair_scores(profiles, variants, variant_gate)
    ids = sorted(profiles)
    seeds = [k for k, r in scores.items() if use_must_link and is_must_link(r)]
    groups = _components(ids, seeds)
    while len(groups) > 1:
        best, bi, bj = tau, -1, -1
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                s = average_score(groups[i], groups[j], scores)
                if s >= best:
                    best, bi, bj = s, i, j
        if bi < 0:
            break
        groups[bi] = groups[bi] + groups[bj]
        del groups[bj]
    return sorted((sorted(g) for g in groups), key=lambda g: (-len(g), g))
