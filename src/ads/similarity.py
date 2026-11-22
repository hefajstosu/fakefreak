"""Similarity entry point: `score(a, b)` is a thin wrapper over the functions in `ads/sim_functions`.

    from ads.similarity import score
    r = score(profile_a, profile_b)
    r == {"score": float in [0,1], "base": same value, "contributions": {feature: weighted contribution},
          "missing": [features skipped because one side had no data], "strong_links": [...]}

Weights, anchor weights and the ignore list come from `config/cluster.yaml` (see `sim_functions/config.py`).
All comparison logic lives in `sim_functions` (per-attribute similarities, weighting, technical anchors,
evidence reporting). Clustering, evaluation and the demo call only `score`.
"""
from typing import Any, Dict

from .sim_functions import compare_all, load_config
from .sim_functions.evidence import strong_links


def score(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    res = compare_all(a, b, weights=cfg["weights"], anchor_stats=cfg["anchor_stats"], supporting=cfg["supporting"])
    s = round(res["score"] or 0.0, 4)
    feats = res["features"]
    return {"score": s, "base": s,
            "contributions": {k: f["contribution"] for k, f in feats.items() if f["contribution"] is not None},
            "missing": [k for k, f in feats.items() if f["similarity"] is None],
            "strong_links": strong_links(a, b)}
