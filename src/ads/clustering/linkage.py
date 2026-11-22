"""Campaigns: must-link pairs merged first, then average-link merging while the mean score between two groups
reaches tau. Average link needs the MEAN over all member pairs, so one strong bridge cannot chain two campaigns
(single link would). Pure Python; fine for the hundreds of articles this project handles (docs/DEPLOYMENT.md)."""
from typing import Dict, Hashable, Iterable, List, Optional, Tuple

from .evidence import joins_alone
from .pairs import Profiles, Scores, pair, pair_scores


def components(ids: Iterable[Hashable], edges: Iterable[Tuple[Hashable, Hashable]]) -> List[list]:
    """Connected components (union-find), in the order of `ids`."""
    ids = list(ids)
    parent = {k: k for k in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: Dict[Hashable, list] = {}
    for k in ids:
        groups.setdefault(find(k), []).append(k)
    return list(groups.values())


def average_score(g1: List[str], g2: List[str], scores: Scores) -> float:
    return sum(pair(scores, a, b)["score"] for a in g1 for b in g2) / (len(g1) * len(g2))


def cluster(profiles: Profiles, tau: float, scores: Optional[Scores] = None,
            use_must_link: bool = True) -> List[List[str]]:
    """Campaigns as sorted id lists, largest first."""
    scores = scores if scores is not None else pair_scores(profiles)
    seeds = [k for k, r in scores.items() if use_must_link and joins_alone(r)]
    groups = components(sorted(profiles), seeds)
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
