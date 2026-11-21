"""Tests for the extraction step. Synthetic data only; no network (MockClient)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ads.llm.client import MockClient, parse_json  # noqa: E402
from ads.llm import extract as ex  # noqa: E402

CASE = {
    "schema_version": "1.0", "case_id": "t1",
    "parts": [
        {"role": "ad_creative", "medium": "image", "text": None, "images": []},
        {"role": "bridge_page", "medium": "html", "text": "Headline of a fake article. " * 3},
        {"role": "offer_page", "medium": "html", "text": "Order form text"},
    ],
    "technical_summary": {"urls_and_domains": ["https://example.test/"], "redirect_chain": ["https://example.test/"],
                          "tracker_ids": ["meta_pixel:123456"], "dom_and_form_clues": ["file:main.js"],
                          "domain_and_cert_metadata": []},
    "resolved_identities": [],
}
CASE["parts"][0]["transcript"] = "spoken words"


def profile(**over):
    p = {
        "detected_language": "pl", "extracted_text_verbatim": "BIG HEADLINE\nClick here",
        "core_narrative": {"ad_goal_scam_type": "fake_investment", "narrative_pattern": "a", "promise_and_mechanism": "b",
                           "call_to_action": "c", "topic": "finance_crypto", "keywords": ["k"], "persuasion_devices": []},
        "entities": {"featured_people": [], "companies_or_institutions": [],
                     "product_or_platform": {"exact_name": None, "generic_category": None},
                     "impersonated_media": [], "amounts_dates_locations": {"amounts": [], "dates": [], "locations": []}},
        "visual_and_production": {"ad_creative_template": None, "landing_page_template": None,
                                  "funnel_stages": ["ad", "decoy_page"], "setting_and_props": [], "visible_logos_and_badges": []},
        "non_grouping_attributes": {"unidentified_people_demographics": []},
        "technical_artifacts": {"urls_and_domains": ["INVENTED"], "redirect_chain": [], "tracker_ids": [],
                                "dom_and_form_clues": [], "domain_and_cert_metadata": [],
                                "ad_library_metadata": {"page_id_or_name": "Some Page", "payer_name": None, "dates_active": None}},
        "canonical_comparison_text": "A neutral summary of the scenario that is long enough to pass.",
    }
    p.update(over)
    return p


def test_parse_json_handles_code_fences_and_noise():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Here you go: {"a": 2} thanks') == {"a": 2}


def test_extract_enforces_code_owned_fields():
    client = MockClient([json.dumps(profile())])
    out = ex.extract(CASE, client)
    # traces come from code, never from the model
    assert out["technical_artifacts"]["urls_and_domains"] == ["https://example.test/"]
    assert out["technical_artifacts"]["tracker_ids"] == ["meta_pixel:123456"]
    assert out["technical_artifacts"]["ad_library_metadata"]["page_id_or_name"] == "Some Page"
    # funnel comes from the case parts (model said ad+decoy_page)
    assert out["visual_and_production"]["funnel_stages"] == ["ad", "bridge_page", "offer_page"]
    # page text and transcript are appended by code with markers
    t = out["extracted_text_verbatim"]
    assert t.startswith("[[AD_CREATIVE]]\nBIG HEADLINE")
    assert "[[BRIDGE_PAGE]]" in t and "[[OFFER_PAGE]]" in t and "[[VIDEO_TRANSCRIPT]]\nspoken words" in t


def test_invalid_profile_gets_one_repair_attempt():
    bad = profile()
    bad["core_narrative"]["ad_goal_scam_type"] = "made_up_type"
    client = MockClient([json.dumps(bad), json.dumps(profile())])
    out = ex.extract(CASE, client)
    assert out["core_narrative"]["ad_goal_scam_type"] == "fake_investment"
    assert len(client.calls) == 2


def test_long_page_text_is_trimmed_with_marker():
    case = json.loads(json.dumps(CASE))
    case["parts"][1]["text"] = "word " * 5000
    t = ex.assemble_text("x", case)
    assert t.count("[...]") == 1 and len(t) < ex.PAGE_CHARS + 500
