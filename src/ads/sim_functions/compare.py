"""Public API: compare two article profiles attribute by attribute.

    from ads.sim_functions import compare_all, compare_to_variants

    result = compare_all(profile_a, profile_b)
    result["score"]                              # weighted score or None
    result["features"]["companies"]["similarity"]

    rows = compare_to_variants(parent_profile, variants_output)   # one result per generated variant

Profiles are plain dicts shaped like schemas/profile.schema.json; variants like variant.schema.json.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from . import attributes as A
from .aggregate import (ANCHOR_WEIGHTS, DEFAULT_WEIGHTS, as_profile, compare_profiles, feature_vector,
                        get)


def compare_all(a: dict, b: dict, weights: Optional[Dict[str, float]] = None,
                embed: Optional[Callable] = None, soft: Optional[Callable] = None,
                anchor_stats: Optional[dict] = None, supporting: Optional[dict] = None) -> dict:
    """Everything known about the similarity of two profiles, as one JSON-compatible dict:

    score          weighted mean over the features present on both sides (None if none are)
    used_weight    total weight behind that score (low = weak evidence)
    features       {name: {"similarity": float|None, "weight": float, "contribution": float|None}}
                   similarity None = not comparable (dropped); contribution = share of the score
    diagnostics    attributes that are deliberately NOT in the score (demographics, language guard)

    weights       override DEFAULT_WEIGHTS/ANCHOR_WEIGHTS (see aggregate.load_weights)
    embed         callable list[str] -> list[vector] for the free-text features (embeddings.E5Embedder)
    soft          optional name-similarity hook for same-sector swaps
    anchor_stats  {'n_docs', 'doc_freq', 'ignore'} for rarity-weighted anchors. Anchors are always
                  included; without stats every shared value weighs the same.
    supporting    {'features', 'min'}: features that count only when they agree (see compare_profiles)
    """
    res = compare_profiles(a, b, weights, embed, soft,
                           anchor_stats=anchor_stats if anchor_stats is not None else {}, supporting=supporting)
    w = weights or {**DEFAULT_WEIGHTS, **ANCHOR_WEIGHTS}
    total = res.used_weight
    features = {}
    for name, sim in res.vector.items():
        weight = w.get(name, 0.0)
        counted = name in res.weights
        features[name] = {
            "similarity": None if sim is None else round(sim, 4),
            "weight": weight,
            "contribution": round(weight * sim / total, 4) if counted and total else None,
        }
    return {
        "score": None if res.score is None else round(res.score, 4),
        "used_weight": round(total, 3),
        "features": features,
        "diagnostics": {
            "detected_language": A.detected_language(a.get("detected_language"), b.get("detected_language")),
            "demographics_similarity": A.demographics_similarity(
                get(a, "non_grouping_attributes.unidentified_people_demographics", []),
                get(b, "non_grouping_attributes.unidentified_people_demographics", [])),
        },
    }


#: Fixed column order of similarity_vector(). Store it next to any saved vectors.
FEATURE_NAMES = tuple(feature_vector({}, {}, anchor_stats={}))


def similarity_vector(a: dict, b: dict, embed: Optional[Callable] = None,
                      soft: Optional[Callable] = None,
                      anchor_stats: Optional[dict] = None) -> Tuple[Tuple[str, ...], List[float]]:
    """Per-feature similarities of two profiles as (FEATURE_NAMES, values), in a fixed order.

    values[i] is in [0, 1], or NaN when feature i is not comparable for this pair (empty or unknown
    on a side). NaN means "no evidence", not "dissimilar": mask it, never treat it as 0.
    Wrap with numpy.array(values) to stack many pairs into a Q x M x F tensor.
    """
    vec = feature_vector(a, b, embed, soft, anchor_stats if anchor_stats is not None else {})
    return FEATURE_NAMES, [math.nan if vec[k] is None else vec[k] for k in FEATURE_NAMES]


def compare_to_variants(parent: dict, variants_output: dict, **kwargs) -> Dict[int, dict]:
    """Compare `parent` with every variant in a variant.schema.json document.

    Each variant is merged onto its parent first (as_profile), so inherited fields such as
    technical_artifacts are present. Returns {variant_index: compare_all(...) result}.
    **kwargs are passed to compare_all.
    """
    return {v.get("variant_index"): compare_all(parent, as_profile(v, parent), **kwargs)
            for v in variants_output.get("variants", [])}


def compare_to_many(query: dict, candidates: Dict[str, dict], **kwargs) -> Dict[str, dict]:
    """Compare one profile with many ready-to-compare profiles ({candidate_id: profile}).
    Sharing one `embed` callable across calls reuses its cache."""
    return {cid: compare_all(query, prof, **kwargs) for cid, prof in candidates.items()}


def format_table(result: dict, title: str = "") -> str:
    """Human-readable table of one compare_all() result (for logs and notebooks)."""
    rows = sorted(result["features"].items(), key=lambda kv: -(kv[1]["contribution"] or -1))
    out = [title] if title else []
    out.append(f"{'feature':<26}{'similarity':>11}{'weight':>8}{'contrib.':>10}")
    out.append("-" * 55)
    for name, f in rows:
        sim = "n/a" if f["similarity"] is None else f"{f['similarity']:.3f}"
        con = "" if f["contribution"] is None else f"{f['contribution']:.3f}"
        out.append(f"{name:<26}{sim:>11}{f['weight']:>8.2f}{con:>10}")
    out.append("-" * 55)
    score = "n/a" if result["score"] is None else f"{result['score']:.3f}"
    out.append(f"{'SCORE':<26}{score:>11}   (weight used: {result['used_weight']})")
    d = result["diagnostics"]
    out.append(f"not in score: language_match={d['detected_language']}  "
               f"demographics_similarity={d['demographics_similarity']}")
    return "\n".join(out)
