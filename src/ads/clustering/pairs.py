"""Pair scores: the N x N similarity table that all grouping works on.

Synthetic variants are optional extra evidence. `variants` is {case_id: [variant profile, ...]} (see
`ads.ablation.load_variants`). A variant is never a node in the table or in any group: it only gives a real
article an extra chance to match. The score of two real articles a, b is the best of
score(a, b), score(a, each variant of b) and score(each variant of a, b), all with the same `score()`.
"""
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from ..similarity import score

Profiles = Dict[str, Dict[str, Any]]
Scores = Dict[Tuple[str, str], Dict[str, Any]]
Variants = Dict[str, List[Dict[str, Any]]]


def best_score(a: Dict[str, Any], b: Dict[str, Any], a_variants: Optional[List[dict]] = None,
               b_variants: Optional[List[dict]] = None, variant_gate: Optional[float] = None,
               stats: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """score(a, b), raised to the best score against either side's variants.

    The result keeps the direct pair's `strong_links` (hard evidence comes from real traces only). `base` is the
    direct score and `via_variant` says where the final score came from: None (direct) or
    "a:<i>" / "b:<i>" (the i-th variant of a or b).

    Variants are only ever compared with the other REAL article, never with each other. `variant_gate` (None = off)
    skips the variant comparisons when the direct score is below it and there is no hard evidence, so hopeless
    pairs cost one comparison instead of 1 + len(variants of a) + len(variants of b). `stats`, if given, counts
    "variant_comparisons" done and "variant_comparisons_skipped".
    """
    res = score(a, b)
    res["via_variant"] = None
    n_var = len(a_variants or []) + len(b_variants or [])
    if variant_gate is not None and res["score"] < variant_gate and not res["strong_links"]:
        if stats is not None:
            stats["variant_comparisons_skipped"] = stats.get("variant_comparisons_skipped", 0) + n_var
        return res
    if stats is not None:
        stats["variant_comparisons"] = stats.get("variant_comparisons", 0) + n_var
    candidates = [("b:%d" % i, score(a, v)) for i, v in enumerate(b_variants or [])]
    candidates += [("a:%d" % i, score(v, b)) for i, v in enumerate(a_variants or [])]
    for tag, r in candidates:
        if r["score"] > res["score"]:
            res.update(score=r["score"], contributions=r["contributions"], missing=r["missing"], via_variant=tag)
    return res


def pair_scores(profiles: Profiles, variants: Optional[Variants] = None, variant_gate: Optional[float] = None,
                stats: Optional[Dict[str, int]] = None) -> Scores:
    """{(id_a, id_b): result} for every unordered pair of REAL articles, ids sorted. See `best_score` for the gate."""
    variants = variants or {}
    return {(a, b): best_score(profiles[a], profiles[b], variants.get(a), variants.get(b), variant_gate, stats)
            for a, b in combinations(sorted(profiles), 2)}


def pair(scores: Scores, a: str, b: str) -> Dict[str, Any]:
    return scores[(a, b)] if (a, b) in scores else scores[(b, a)]
