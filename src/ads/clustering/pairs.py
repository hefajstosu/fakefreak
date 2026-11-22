"""The N x N pair table all grouping works on.

With synthetic variants ({case id: [variant profiles]}) the score of two real articles a, b is the best of
score(a, b), score(a, each variant of b) and score(each variant of a, b); variants are never compared with each other
and never become nodes. `via_variant` says where the score came from (None, "a:<i>" or "b:<i>").
"""
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from ..similarity import score

Profiles = Dict[str, Dict[str, Any]]
Scores = Dict[Tuple[str, str], Dict[str, Any]]
Variants = Dict[str, List[Dict[str, Any]]]


def best_score(a: Dict[str, Any], b: Dict[str, Any], a_variants: Optional[List[dict]] = None,
               b_variants: Optional[List[dict]] = None) -> Dict[str, Any]:
    """score(a, b), raised to the best score against either side's variants; the evidence stays the real pair's."""
    res = dict(score(a, b), via_variant=None)
    tries = [("b:%d" % i, score(a, v)) for i, v in enumerate(b_variants or [])]
    tries += [("a:%d" % i, score(v, b)) for i, v in enumerate(a_variants or [])]
    for tag, r in tries:
        if r["score"] > res["score"]:
            res.update(score=r["score"], contributions=r["contributions"], missing=r["missing"], via_variant=tag)
    return res


def pair_scores(profiles: Profiles, variants: Optional[Variants] = None) -> Scores:
    """{(id_a, id_b): best_score result} for every unordered pair of real articles, ids sorted."""
    variants = variants or {}
    return {(a, b): best_score(profiles[a], profiles[b], variants.get(a), variants.get(b))
            for a, b in combinations(sorted(profiles), 2)}


def pair(scores: Scores, a: str, b: str) -> Dict[str, Any]:
    return scores[(a, b)] if (a, b) in scores else scores[(b, a)]
