"""Synthetic profiles for the tests (schemas/profile.schema.json shaped; no sample data)."""

OTHER = dict(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")  # an unrelated scheme


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


def make(scam="fake_investment", topic="finance_crypto", product="AlphaPlat", tracker=None, text="invest platform deposit", clues=None):
    p = profile()
    p["core_narrative"].update(ad_goal_scam_type=scam, topic=topic)
    p["entities"]["product_or_platform"]["exact_name"] = product
    p["canonical_comparison_text"] = text + " scenario summary long enough"
    p["technical_artifacts"]["tracker_ids"] = [tracker] if tracker else []
    p["technical_artifacts"]["dom_and_form_clues"] = clues or []
    p["technical_artifacts"]["urls_and_domains"] = []  # no accidental shared domain between test profiles
    p["technical_artifacts"]["ad_library_metadata"]["page_id_or_name"] = None  # nor a shared sponsoring page
    return p
