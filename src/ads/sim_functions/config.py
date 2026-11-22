"""Similarity settings from config/cluster.yaml, validated and cached.

    cfg = load_config()
    cfg["weights"]      {feature: weight}: the file's `weights` and `anchors` over features.DEFAULT_WEIGHTS
    cfg["ignore"]       values never used as anchor evidence (`ignore_values`)
    cfg["supporting"]   {"features": names, "min": m} (`supporting_features`, `supporting_min`)

An unknown feature name or a negative weight is an error: a typo would otherwise silently do nothing.
"""
import os
from functools import lru_cache
from typing import Optional

from ..paths import CONFIG
from .features import ANCHORS, DEFAULT_WEIGHTS, FEATURES

DEFAULT_PATH = os.path.join(CONFIG, "cluster.yaml")


def _build(raw: dict, path: str) -> dict:
    weights = {**(raw.get("weights") or {}), **(raw.get("anchors") or {})}
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"{path}: unknown weight name(s) {sorted(unknown)}; valid: {sorted(DEFAULT_WEIGHTS)}")
    for k, v in weights.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            raise ValueError(f"{path}: weight '{k}' must be a number >= 0, got {v!r}")
    supporting = raw.get("supporting_features") or []
    bad = set(supporting) - set(FEATURES)
    if bad:
        raise ValueError(f"{path}: unknown supporting feature(s) {sorted(bad)}; valid: {sorted(FEATURES)}")
    return {"weights": {**DEFAULT_WEIGHTS, **weights}, "ignore": frozenset(raw.get("ignore_values") or []),
            "supporting": {"features": frozenset(supporting), "min": float(raw.get("supporting_min", 0.5))}}


@lru_cache(maxsize=None)
def _load(path: str) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return _build(yaml.safe_load(f) or {}, path)


def load_config(path: Optional[str] = None) -> dict:
    """Parsed and validated settings (cached per path); a missing file means the defaults."""
    path = path or DEFAULT_PATH
    return _load(path) if os.path.exists(path) else _build({}, path)


__all__ = ["ANCHORS", "load_config"]
