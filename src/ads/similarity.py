"""score(a, b): the similarity of two article profiles, the contract every other module uses.

    r = score(profile_a, profile_b)
    r["score"]          in [0, 1], the weighted mean of the features present on both sides
    r["contributions"]  {feature: share of the score} for the features counted
    r["missing"]        features that could not be compared (no data on a side)
    r["strong_links"]   shared traces in words (sim_functions/evidence.py); they never change the number

Weights, ignored values and supporting features come from config/cluster.yaml (sim_functions/config.py).
"""
from typing import Any, Dict

from .sim_functions import compare_all, load_config
from .sim_functions.evidence import strong_links


def score(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    res = compare_all(a, b, weights=cfg["weights"], ignore=cfg["ignore"], supporting=cfg["supporting"])
    feats = res["features"]
    return {"score": res["score"] or 0.0,
            "contributions": {k: f["contribution"] for k, f in feats.items() if f["contribution"] is not None},
            "missing": [k for k, f in feats.items() if f["similarity"] is None],
            "strong_links": strong_links(a, b)}
