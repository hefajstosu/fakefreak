"""Checks of LLM-generated variants against their parent profile (used by generate.py): locked fields kept, exact k,
no duplicates, URLs and [[PART]] markers kept, text patches resolvable, demographics-only variants unchanged."""
import json
import re

SLOTS = {
    "entities.featured_people", "entities.companies_or_institutions",
    "entities.impersonated_media", "visual_and_production.setting_and_props",
    "non_grouping_attributes.unidentified_people_demographics",
    "entities.product_or_platform", "entities.amounts_dates_locations",
    "core_narrative.call_to_action", "core_narrative.keywords",
}
DEMO = "non_grouping_attributes.unidentified_people_demographics"
URL_RE = re.compile(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s\"')]*)?", re.I)


def get(d, path):
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def resolve_text(parent_text, v):
    """Return (edited text, errors). Supports full-text and patch modes."""
    errs = []
    if v.get("edited_source_text") is not None:
        if v.get("text_patches"):
            errs.append("both edited_source_text and text_patches given")
        return v["edited_source_text"], errs
    text = parent_text
    for i, patch in enumerate(v.get("text_patches") or []):
        span = patch.get("original_span", "")
        if not span or parent_text.count(span) != 1:
            errs.append(f"patch {i}: original_span must occur exactly once in parent text")
            continue
        text = text.replace(span, patch.get("replacement", ""), 1)
    return text, errs


def validate(parent, out, k=None):
    errors = []
    seen = set()
    p_text = parent.get("extracted_text_verbatim", "")
    p_urls = set(URL_RE.findall(p_text))
    p_markers = re.findall(r"\[\[[A-Z_]+\]\]", p_text)
    for v in out.get("variants", []):
        tag = f"variant {v.get('variant_index')}"
        mf = v.get("mutated_fields", [])
        if not set(mf) <= SLOTS:
            errors.append(f"{tag}: unknown slot(s) {set(mf) - SLOTS}")
        if len(mf) != len(set(mf)):
            errors.append(f"{tag}: duplicate slot in mutated_fields")
        if len(mf) != v.get("k_achieved"):
            errors.append(f"{tag}: len(mutated_fields)={len(mf)} != k_achieved")
        if k is not None and len(mf) > k:
            errors.append(f"{tag}: mutated {len(mf)} slots, k={k}")
        if k is not None and v.get("k_achieved", 0) < k and not out.get("generation_notes"):
            errors.append(f"{tag}: k_achieved < k without generation_notes")
        if v.get("synthetic") is not True:
            errors.append(f"{tag}: synthetic flag missing")
        for path in ("core_narrative.ad_goal_scam_type", "core_narrative.persuasion_devices",
                     "visual_and_production.ad_creative_template",
                     "visual_and_production.landing_page_template",
                     "visual_and_production.funnel_stages"):
            if get(v, path) != get(parent, path):
                errors.append(f"{tag}: locked field {path} changed")
        if v.get("detected_language") != parent.get("detected_language"):
            errors.append(f"{tag}: detected_language changed")
        if "technical_artifacts" in v:
            errors.append(f"{tag}: technical_artifacts must not be output")
        text, terr = resolve_text(p_text, v)
        errors.extend(f"{tag}: {e}" for e in terr)
        for u in p_urls:
            if u not in text:
                errors.append(f"{tag}: URL/domain '{u}' missing or altered in text")
        if re.findall(r"\[\[[A-Z_]+\]\]", text) != p_markers:
            errors.append(f"{tag}: [[PART]] markers changed")
        if mf == [DEMO]:
            if v.get("canonical_comparison_text") != parent.get("canonical_comparison_text"):
                errors.append(f"{tag}: demographics-only variant changed canonical text")
            if text != p_text:
                errors.append(f"{tag}: demographics-only variant changed source text")
        if DEMO not in mf and get(v, DEMO) != get(parent, DEMO):
            errors.append(f"{tag}: demographics changed but slot not logged")
        sig = json.dumps(sorted((m["field"], json.dumps(m["new_value"], sort_keys=True))
                                for m in v.get("mutation_log", [])))
        if sig in seen:
            errors.append(f"{tag}: duplicates an earlier variant")
        seen.add(sig)
    return errors

