"""Similarity of extracted ad profiles (and of profiles vs. synthetic variants).

    from ads.sim_functions import compare_all, compare_to_variants
    res = compare_all(profile_a, profile_b)
    res["score"], res["features"]
"""
from .aggregate import (ANCHOR_WEIGHTS, DEFAULT_WEIGHTS, Result, as_profile, compare_profiles,
                        feature_vector, load_weights)
from .config import load_config
from .compare import (FEATURE_NAMES, compare_all, compare_to_many, compare_to_variants,
                      format_table, similarity_vector)

__all__ = ["similarity_vector", "FEATURE_NAMES", "compare_all", "compare_to_variants",
           "compare_to_many", "format_table",
           "compare_profiles", "feature_vector", "as_profile", "load_weights", "load_config", "Result",
           "DEFAULT_WEIGHTS", "ANCHOR_WEIGHTS"]
