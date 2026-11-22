"""Combine per-attribute similarities of two profiles into a feature vector and one weighted score."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from . import attributes as A


def get(d, path, default=None):
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return default if d is None else d


# Weights from config/cluster.yaml. Keys marked (*) are not in that file yet: first guesses.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "scam_type": 1.0, "narrative": 0.8, "promise": 0.8, "product_name": 1.0,
    "featured_people": 0.8, "companies": 0.8, "impersonated_media": 0.8,
    "ad_creative_template": 0.8, "landing_page_template": 0.8, "persuasion_devices": 0.5,
    "call_to_action": 0.5, "setting_and_props": 0.3, "amounts_dates_locations": 0.2,
    "embedding": 0.8,
    "topic": 0.5,          # (*)
    "funnel_stages": 0.3,  # (*)
    "keywords": 0.3,       # (*)
    "page_structure": 0.8,  # (*) same weight as landing_page_template, its LLM counterpart
    "logos_and_badges": 0.0,  # (*) reported, not scored: a shared TV channel logo is not evidence (gold: 48 > 10)
}
# Exact-match technical anchors; computed only when anchor_stats is passed (see below).
ANCHOR_WEIGHTS: Dict[str, float] = {
    "tracker_ids": 1.0, "redirect_chain_domains": 0.9, "dom_and_form_clues": 0.8,
    "ad_library_page_name": 0.7,
    "page_assets": 0.8,    # same weight as dom_and_form_clues: another first-party trace of how the page was built
    "url_template": 0.5,   # the operator's own tracking parameters / ad campaign IDs in the funnel URLs
    "infra_metadata": 0.0,  # registration batch, non-CDN hosting / name servers, certificate neighbours: reported,
                            # not scored until shared values can be validated (no sample domains share them)
}


def load_weights(path: Optional[str] = None):
    """(feature weights, anchor weights) from cluster.yaml (validated; see config.load_config)."""
    from .config import load_config
    w = load_config(path)["weights"]
    return {k: w[k] for k in DEFAULT_WEIGHTS}, {k: w[k] for k in ANCHOR_WEIGHTS}


def as_profile(variant: dict, parent: dict) -> dict:
    """Make a variant comparable to a profile: overlay its sections on the parent, which supplies
    the inherited fields (technical_artifacts, and the text if you resolve patches yourself)."""
    p = copy.deepcopy(parent)
    for key in ("detected_language", "core_narrative", "entities", "visual_and_production",
                "non_grouping_attributes", "canonical_comparison_text"):
        if key in variant:
            p[key] = copy.deepcopy(variant[key])
    return p


@dataclass
class Result:
    vector: Dict[str, Optional[float]]   # per-feature similarity; None = not comparable, dropped
    score: Optional[float]               # weighted mean over features present on both sides
    used_weight: float = 0.0             # total weight behind the score (low = weak evidence)
    weights: Dict[str, float] = field(default_factory=dict)


def feature_vector(a: dict, b: dict, embed: Optional[Callable] = None, soft: Optional[Callable] = None,
                   anchor_stats: Optional[dict] = None) -> Dict[str, Optional[float]]:
    """Per-feature similarity of two profile-shaped dicts.

    anchor_stats (optional): {'n_docs': int, 'doc_freq': {value: count}, 'ignore': set}. Anchors are
    inherited by variants, so compute them once per parent rather than per variant when you can.
    """
    v = {
        "scam_type": A.scam_type(get(a, "core_narrative.ad_goal_scam_type"), get(b, "core_narrative.ad_goal_scam_type")),
        "topic": A.topic(get(a, "core_narrative.topic"), get(b, "core_narrative.topic")),
        "ad_creative_template": A.ad_creative_template(get(a, "visual_and_production.ad_creative_template"),
                                                       get(b, "visual_and_production.ad_creative_template")),
        "landing_page_template": A.landing_page_template(get(a, "visual_and_production.landing_page_template"),
                                                         get(b, "visual_and_production.landing_page_template")),
        "funnel_stages": A.funnel_stages(get(a, "visual_and_production.funnel_stages", []),
                                         get(b, "visual_and_production.funnel_stages", [])),
        "persuasion_devices": A.persuasion_devices(get(a, "core_narrative.persuasion_devices", []),
                                                   get(b, "core_narrative.persuasion_devices", [])),
        "featured_people": A.featured_people(get(a, "entities.featured_people", []),
                                             get(b, "entities.featured_people", [])),
        "companies": A.companies(get(a, "entities.companies_or_institutions", []),
                                 get(b, "entities.companies_or_institutions", []), soft),
        "impersonated_media": A.impersonated_media(get(a, "entities.impersonated_media", []),
                                                   get(b, "entities.impersonated_media", []), soft),
        "product_name": A.product_or_platform(get(a, "entities.product_or_platform"),
                                              get(b, "entities.product_or_platform")),
        "setting_and_props": A.setting_and_props(get(a, "visual_and_production.setting_and_props", []),
                                                 get(b, "visual_and_production.setting_and_props", []), soft),
        "amounts_dates_locations": A.amounts_dates_locations(get(a, "entities.amounts_dates_locations"),
                                                             get(b, "entities.amounts_dates_locations")),
        "keywords": A.keywords(get(a, "core_narrative.keywords", []), get(b, "core_narrative.keywords", [])),
        "narrative": A.narrative_pattern(get(a, "core_narrative.narrative_pattern"),
                                         get(b, "core_narrative.narrative_pattern"), embed),
        "promise": A.promise_and_mechanism(get(a, "core_narrative.promise_and_mechanism"),
                                           get(b, "core_narrative.promise_and_mechanism"), embed),
        "call_to_action": A.call_to_action(get(a, "core_narrative.call_to_action"),
                                           get(b, "core_narrative.call_to_action"), embed),
        "embedding": A.canonical_comparison_text(a.get("canonical_comparison_text"),
                                                 b.get("canonical_comparison_text"), embed),
        "logos_and_badges": A.logos_and_badges(get(a, "visual_and_production.visible_logos_and_badges", []),
                                               get(b, "visual_and_production.visible_logos_and_badges", [])),
        "page_structure": A.page_structure(get(a, "technical_artifacts.page_fingerprints"),
                                           get(b, "technical_artifacts.page_fingerprints")),
    }
    if anchor_stats is not None:
        ta, tb = a.get("technical_artifacts", {}), b.get("technical_artifacts", {})
        kw = dict(doc_freq=anchor_stats.get("doc_freq"), n_docs=anchor_stats.get("n_docs"),
                  ignore=frozenset(anchor_stats.get("ignore", ())))
        v["tracker_ids"] = A.anchor_similarity(ta.get("tracker_ids"), tb.get("tracker_ids"), **kw)
        v["redirect_chain_domains"] = A.anchor_similarity(A.domains(ta.get("redirect_chain")),
                                                          A.domains(tb.get("redirect_chain")), **kw)
        v["dom_and_form_clues"] = A.anchor_similarity(ta.get("dom_and_form_clues"),
                                                      tb.get("dom_and_form_clues"), **kw)
        v["ad_library_page_name"] = A.ad_library_page_name(
            get(ta, "ad_library_metadata.page_id_or_name"), get(tb, "ad_library_metadata.page_id_or_name"))
        v["url_template"] = A.anchor_similarity(
            A.url_tokens((ta.get("redirect_chain") or []) + (ta.get("urls_and_domains") or [])),
            A.url_tokens((tb.get("redirect_chain") or []) + (tb.get("urls_and_domains") or [])), **kw)
        v["infra_metadata"] = A.anchor_similarity(A.infra_tokens(ta.get("domain_and_cert_metadata")),
                                                  A.infra_tokens(tb.get("domain_and_cert_metadata")), **kw)
        v["page_assets"] = A.anchor_similarity(get(ta, "page_fingerprints.images"), get(tb, "page_fingerprints.images"),
                                               **kw)
    return v


def compare_profiles(a: dict, b: dict, weights: Optional[Dict[str, float]] = None,
                     embed: Optional[Callable] = None, soft: Optional[Callable] = None,
                     anchor_stats: Optional[dict] = None, supporting: Optional[dict] = None) -> Result:
    """Weighted mean of the feature vector, renormalised over features present on both sides.

    Demographics are deliberately absent (weight 0, see attributes.demographics_similarity).
    supporting: {"features": names, "min": float}. A supporting feature counts only when it agrees (similarity >=
    min); a disagreement is dropped like missing data. For surface elements operators swap on purpose (people,
    product, companies, outlets): a match is evidence, a difference is not evidence against.
    """
    w = dict(weights or {**DEFAULT_WEIGHTS, **ANCHOR_WEIGHTS})
    vec = feature_vector(a, b, embed, soft, anchor_stats)
    sup = supporting or {}
    skip = {k for k in sup.get("features", ()) if vec.get(k) is not None and vec[k] < sup.get("min", 0.5)}
    used = {k: w.get(k, 0.0) for k, s in vec.items() if s is not None and w.get(k, 0.0) > 0 and k not in skip}
    total = sum(used.values())
    score = sum(w[k] * vec[k] for k in used) / total if total else None
    return Result(vector=vec, score=score, used_weight=total, weights=used)
