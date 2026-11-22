"""The similarity of two ad profiles: per-feature similarities, their weighted mean, and the evidence behind it.

    primitives.py   generic measures (exact, Jaccard, names, numbers, text)
    attributes.py   measures for people, product, amounts, page fingerprints and the tokens of technical traces
    features.py     the feature table and compare_all(): the weighted, missing-data-aware mean
    evidence.py     strong_links(): shared traces stated in words (reporting; grouping reads them as must-links)
    config.py       weights, ignored values and supporting features from config/cluster.yaml
"""
from .config import load_config
from .features import ANCHORS, DEFAULT_WEIGHTS, FEATURES, compare_all, feature_vector, get

__all__ = ["load_config", "ANCHORS", "DEFAULT_WEIGHTS", "FEATURES", "compare_all", "feature_vector", "get"]
