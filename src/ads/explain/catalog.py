"""What the explanations know about features and evidence: groups, how each feature's values are shown, evidence kinds."""
from typing import Any, Dict, List, Sequence, Tuple

from .. import clustering

# Feature groups, in display order (the same split as the channel ablation in evaluation/robustness.py).
GROUPS = {
    "infrastructure": "trackers, redirect domains, endpoints and files, page images, tracking template, domain facts",
    "core": "scam type and topic",
    "templates": "ad and landing-page templates, funnel, page structure",
    "persuasion": "persuasion devices",
    "entities": "product, people, companies, impersonated media",
    "text": "narrative, promise, call to action, summary, keywords",
    "surface": "props, amounts, dates, places, logos",
}
# feature -> (group, how its values are shown (values.py), path in the profile)
FEATURES: Dict[str, Tuple[str, str, str]] = {
    "tracker_ids": ("infrastructure", "anchor", "technical_artifacts.tracker_ids"),
    "redirect_chain_domains": ("infrastructure", "domains", "technical_artifacts.redirect_chain"),
    "dom_and_form_clues": ("infrastructure", "anchor", "technical_artifacts.dom_and_form_clues"),
    "ad_library_page_name": ("infrastructure", "enum", "technical_artifacts.ad_library_metadata.page_id_or_name"),
    "page_assets": ("infrastructure", "images", "technical_artifacts.page_fingerprints"),
    "url_template": ("infrastructure", "url", "technical_artifacts"),
    "infra_metadata": ("infrastructure", "infra", "technical_artifacts.domain_and_cert_metadata"),
    "scam_type": ("core", "enum", "core_narrative.ad_goal_scam_type"),
    "topic": ("core", "enum", "core_narrative.topic"),
    "ad_creative_template": ("templates", "enum", "visual_and_production.ad_creative_template"),
    "landing_page_template": ("templates", "enum", "visual_and_production.landing_page_template"),
    "funnel_stages": ("templates", "set", "visual_and_production.funnel_stages"),
    "page_structure": ("templates", "structure", "technical_artifacts.page_fingerprints"),
    "persuasion_devices": ("persuasion", "set", "core_narrative.persuasion_devices"),
    "product_name": ("entities", "product", "entities.product_or_platform"),
    "featured_people": ("entities", "people", "entities.featured_people"),
    "companies": ("entities", "names", "entities.companies_or_institutions"),
    "impersonated_media": ("entities", "names", "entities.impersonated_media"),
    "narrative": ("text", "text", "core_narrative.narrative_pattern"),
    "promise": ("text", "text", "core_narrative.promise_and_mechanism"),
    "call_to_action": ("text", "text", "core_narrative.call_to_action"),
    "embedding": ("text", "text", "canonical_comparison_text"),
    "keywords": ("text", "names", "core_narrative.keywords"),
    "setting_and_props": ("surface", "names", "visual_and_production.setting_and_props"),
    "amounts_dates_locations": ("surface", "amounts", "entities.amounts_dates_locations"),
    "logos_and_badges": ("surface", "names", "visual_and_production.visible_logos_and_badges"),
}
# strong_links label prefix (sim_functions/evidence.py) -> evidence kind shown by the panel
EVIDENCE_KINDS = (("shared tracker ID", "tracker"), ("shared session/form endpoint", "endpoint"),
                  ("shared page images", "images"), ("same ad campaign ID", "adid"),
                  ("same tracking template", "tracking"), ("domains on one certificate", "certificate"),
                  ("shared distinctive script/style file", "file"), ("shared domain", "domain"),
                  ("same sponsoring page", "page"))


def evidence_items(links: Sequence[str]) -> List[Dict[str, Any]]:
    """strong_links strings -> [{"kind", "value", "must_link", "family_link", "text"}]; must_link joins a campaign on
    its own, family_link a family of campaigns."""
    out = []
    for s in links:
        kind = next((k for prefix, k in EVIDENCE_KINDS if s.startswith(prefix)), "other")
        out.append({"kind": kind, "value": s.split(": ", 1)[1] if ": " in s else s,
                    "must_link": clustering.is_must_link({"strong_links": [s]}),
                    "family_link": clustering.is_family_link({"strong_links": [s]}), "text": s})
    return out
