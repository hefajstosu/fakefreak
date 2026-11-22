"""The features of a pair of profiles and their weighted mean: the score.

FEATURES lists every content feature (similarity function, path in the profile); ANCHORS lists the exact-match
technical traces (tokens of the raw value, path), compared by attributes.anchor_similarity. Weights come from
config/cluster.yaml (config.py); a feature of weight 0 is computed and explained but not scored.
"""
from typing import Any, Callable, Dict, Optional, Tuple

from ..preprocess.domain_meta import linking_facts
from ..urls import domains
from . import attributes as A
from .primitives import closed_set, exact, set_similarity, text_similarity

FEATURES: Dict[str, Tuple[Callable, str]] = {
    "scam_type": (exact, "core_narrative.ad_goal_scam_type"),
    "topic": (exact, "core_narrative.topic"),
    "narrative": (text_similarity, "core_narrative.narrative_pattern"),
    "promise": (text_similarity, "core_narrative.promise_and_mechanism"),
    "call_to_action": (text_similarity, "core_narrative.call_to_action"),
    "keywords": (set_similarity, "core_narrative.keywords"),
    "persuasion_devices": (closed_set, "core_narrative.persuasion_devices"),
    "summary": (text_similarity, "canonical_comparison_text"),
    "featured_people": (A.featured_people, "entities.featured_people"),
    "companies": (set_similarity, "entities.companies_or_institutions"),
    "impersonated_media": (set_similarity, "entities.impersonated_media"),
    "product_name": (A.product_or_platform, "entities.product_or_platform"),
    "amounts_dates_locations": (A.amounts_dates_locations, "entities.amounts_dates_locations"),
    "ad_creative_template": (exact, "visual_and_production.ad_creative_template"),
    "landing_page_template": (exact, "visual_and_production.landing_page_template"),
    "funnel_stages": (closed_set, "visual_and_production.funnel_stages"),
    "setting_and_props": (set_similarity, "visual_and_production.setting_and_props"),
    "logos_and_badges": (set_similarity, "visual_and_production.visible_logos_and_badges"),
    "page_structure": (A.page_structure, "technical_artifacts.page_fingerprints"),
    "ad_library_page_name": (A.page_name, "technical_artifacts.ad_library_metadata.page_id_or_name"),
}


def _values(x) -> list:
    return list(x or [])


ANCHORS: Dict[str, Tuple[Callable, str]] = {
    "tracker_ids": (_values, "technical_artifacts.tracker_ids"),
    "redirect_chain_domains": (domains, "technical_artifacts.redirect_chain"),
    "dom_and_form_clues": (_values, "technical_artifacts.dom_and_form_clues"),
    "page_assets": (_values, "technical_artifacts.page_fingerprints.images"),
    "url_template": (A.tracking_tokens, "technical_artifacts"),
    "infra_metadata": (linking_facts, "technical_artifacts.domain_and_cert_metadata"),  # facts that can link
}
# First weights (the file config/cluster.yaml overrides them). Same-weight choices are by analogy, not fitted.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "scam_type": 1.0, "topic": 0.5, "narrative": 0.8, "promise": 0.8, "call_to_action": 0.5, "keywords": 0.3,
    "persuasion_devices": 0.5, "summary": 0.8, "featured_people": 0.8, "companies": 0.8, "impersonated_media": 0.8,
    "product_name": 1.0, "amounts_dates_locations": 0.2, "ad_creative_template": 0.8, "landing_page_template": 0.8,
    "funnel_stages": 0.3, "setting_and_props": 0.3, "logos_and_badges": 0.0, "page_structure": 0.8,
    "ad_library_page_name": 0.7, "tracker_ids": 1.0, "redirect_chain_domains": 0.9, "dom_and_form_clues": 0.8,
    "page_assets": 0.8, "url_template": 0.5, "infra_metadata": 0.0,
}


def get(d: Any, path: str, default=None):
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return default if d is None else d


def feature_vector(a: dict, b: dict, ignore: frozenset = frozenset()) -> Dict[str, Optional[float]]:
    """Similarity of every feature of two profiles; None where a feature cannot be compared."""
    v = {name: fn(get(a, path), get(b, path)) for name, (fn, path) in FEATURES.items()}
    v.update({name: A.anchor_similarity(tokens(get(a, path)), tokens(get(b, path)), ignore)
              for name, (tokens, path) in ANCHORS.items()})
    return v


def compare_all(a: dict, b: dict, weights: Optional[Dict[str, float]] = None, ignore: frozenset = frozenset(),
                supporting: Optional[dict] = None) -> Dict[str, Any]:
    """The score of two profiles with its parts:
        score        weighted mean over the features present on both sides (None if none is)
        used_weight  total weight behind it
        features     {name: {"similarity", "weight", "contribution"}}; contribution is the feature's share of the
                     score, None when the feature is not counted (missing, weight 0, or a supporting feature that
                     disagrees)
    supporting = {"features": names, "min": m}: such a feature counts only when its similarity reaches m; a
    disagreement is dropped like missing data (for surface details operators swap on purpose).
    Demographics of unidentified people are never read (CLAUDE.md rule 5)."""
    w = weights or DEFAULT_WEIGHTS
    vec = feature_vector(a, b, ignore)
    sup = supporting or {}
    skip = {k for k in sup.get("features", ()) if vec.get(k) is not None and vec[k] < sup.get("min", 0.5)}
    used = {k: w.get(k, 0.0) for k, s in vec.items() if s is not None and w.get(k, 0.0) > 0 and k not in skip}
    total = sum(used.values())
    score = sum(used[k] * vec[k] for k in used) / total if total else None
    return {"score": None if score is None else round(score, 4), "used_weight": round(total, 3),
            "features": {k: {"similarity": None if s is None else round(s, 4), "weight": w.get(k, 0.0),
                             "contribution": round(used[k] * s / total, 4) if k in used else None}
                         for k, s in vec.items()}}
