"""What the explanations know about features and evidence: feature groups, how each feature's values are shown,
evidence kinds."""
from typing import Any, Dict, List, Sequence, Tuple

from .. import clustering
from ..sim_functions import ANCHORS, FEATURES as SIMILARITY_FEATURES
from ..sim_functions.evidence import kind_of

# Feature groups, in display order.
GROUPS = {
    "infrastructure": "trackers, redirect domains, endpoints and files, page images, tracking template, domain facts",
    "core": "scam type and topic",
    "templates": "ad and landing-page templates, funnel, page structure",
    "persuasion": "persuasion devices",
    "entities": "product, people, companies, impersonated media",
    "text": "narrative, promise, call to action, summary, keywords",
    "surface": "props, amounts, dates, places, logos",
}
# feature -> (group, how its values are shown: a kind of values.values)
SHOWN: Dict[str, Tuple[str, str]] = {
    "tracker_ids": ("infrastructure", "anchor"), "redirect_chain_domains": ("infrastructure", "domains"),
    "dom_and_form_clues": ("infrastructure", "anchor"), "ad_library_page_name": ("infrastructure", "enum"),
    "page_assets": ("infrastructure", "images"), "url_template": ("infrastructure", "url"),
    "infra_metadata": ("infrastructure", "infra"),
    "scam_type": ("core", "enum"), "topic": ("core", "enum"),
    "ad_creative_template": ("templates", "enum"), "landing_page_template": ("templates", "enum"),
    "funnel_stages": ("templates", "set"), "page_structure": ("templates", "structure"),
    "persuasion_devices": ("persuasion", "set"),
    "product_name": ("entities", "product"), "featured_people": ("entities", "people"),
    "companies": ("entities", "names"), "impersonated_media": ("entities", "names"),
    "narrative": ("text", "text"), "promise": ("text", "text"), "call_to_action": ("text", "text"),
    "summary": ("text", "text"), "keywords": ("text", "names"),
    "setting_and_props": ("surface", "names"), "amounts_dates_locations": ("surface", "amounts"),
    "logos_and_badges": ("surface", "names"),
}
# feature -> (group, kind, path in the profile); the path is the similarity's own (sim_functions/features.py)
FEATURES: Dict[str, Tuple[str, str, str]] = {
    name: (*SHOWN[name], path) for name, (_, path) in {**SIMILARITY_FEATURES, **ANCHORS}.items()}


def evidence_items(links: Sequence[str]) -> List[Dict[str, Any]]:
    """strong_links strings -> [{"kind", "value", "must_link", "family_link", "text"}]; must_link joins a campaign on
    its own, family_link a family of campaigns."""
    return [{"kind": kind_of(s), "value": s.split(": ", 1)[1] if ": " in s else s,
             "must_link": clustering.is_must_link({"strong_links": [s]}),
             "family_link": clustering.is_family_link({"strong_links": [s]}), "text": s} for s in links]
