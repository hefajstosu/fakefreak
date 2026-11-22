"""Similarity settings from config/cluster.yaml: feature weights, anchor weights and the ignore list.

    cfg = load_config()                # cached; cfg["weights"] is what compare_all(weights=...) takes
    cfg["anchor_stats"]                # {"ignore": frozenset(...)} for compare_all(anchor_stats=...)

Keys in the file override the defaults in aggregate.py; keys the file leaves out keep their default. An unknown
weight name is an error (a typo would otherwise silently do nothing).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from ..paths import CONFIG
from .aggregate import ANCHOR_WEIGHTS, DEFAULT_WEIGHTS

DEFAULT_PATH = os.path.join(CONFIG, "cluster.yaml")


def _build(raw: dict, path: str) -> dict:
    feature_w, anchor_w = raw.get("weights") or {}, raw.get("anchors") or {}
    unknown = (set(feature_w) - set(DEFAULT_WEIGHTS)) | (set(anchor_w) - set(ANCHOR_WEIGHTS))
    if unknown:
        raise ValueError(f"{path}: unknown weight name(s) {sorted(unknown)}; "
                         f"valid: {sorted(set(DEFAULT_WEIGHTS) | set(ANCHOR_WEIGHTS))}")
    for k, v in {**feature_w, **anchor_w}.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            raise ValueError(f"{path}: weight '{k}' must be a number >= 0, got {v!r}")
    supporting = raw.get("supporting_features") or []
    bad = set(supporting) - set(DEFAULT_WEIGHTS)
    if bad:
        raise ValueError(f"{path}: unknown supporting feature(s) {sorted(bad)}; valid: {sorted(DEFAULT_WEIGHTS)}")
    return {
        "weights": {**DEFAULT_WEIGHTS, **ANCHOR_WEIGHTS, **feature_w, **anchor_w},
        "supporting": {"features": frozenset(supporting), "min": float(raw.get("supporting_min", 0.5))},
        "anchor_stats": {"ignore": frozenset(raw.get("ignore_values") or [])},
        "thresholds": dict(raw.get("thresholds") or {}),
        "path": path,
    }


@lru_cache(maxsize=None)
def _load(path: str) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return _build(yaml.safe_load(f) or {}, path)


def load_config(path: Optional[str] = None) -> dict:
    """Parsed and validated settings (cached per path). A missing file means the defaults in aggregate.py."""
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        return _build({}, path)
    return _load(path)
