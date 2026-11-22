"""ads.similarity on synthetic profiles: score, missing data, evidence."""
import copy

from ads.similarity import score
from factory import make


def test_identical_profiles_score_one():
    a = make()
    assert score(a, copy.deepcopy(a))["score"] > 0.95


def test_different_scam_type_scores_much_lower():
    a, b = make(), make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")
    assert score(a, b)["score"] < 0.6 < score(a, copy.deepcopy(a))["score"]


def test_shared_tracker_is_reported_and_raises_score_when_content_differs():
    a = make(tracker="meta_pixel:111")
    b = make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor", tracker="meta_pixel:111")
    r = score(a, b)
    no_tracker = score(make(), make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor"))
    assert any("tracker" in s for s in r["strong_links"]) and r["score"] > no_tracker["score"]


def test_missing_features_are_skipped_not_counted_as_zero():
    a, b = make(), make()
    a["visual_and_production"]["landing_page_template"] = None
    r = score(a, b)
    assert "landing_page_template" in r["missing"] and r["score"] > 0.95


def test_scanned_endpoint_paths_match_recorded_post_endpoints():
    # HAR-derived clue (observed POST with ids) vs URL-scan clue (path written in a script): same platform prefix
    har = make(clues=["POST site-a.test/api/v1/trigger/field/<uuid>/ fields=x", "POST site-a.test/api/v1/agent/persist-session-record/<uuid>/<uuid> fields=y"])
    scan = make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor",
                clues=["api:/api/v1/trigger/field/", "api:/api/v1/agent/persist-session-record/", "api:/api/v1/pwa/manifest/"])
    r = score(har, scan)   # different content; the shared endpoint prefixes are reported as evidence
    assert any("endpoint" in s for s in r["strong_links"])


def test_a_single_shared_generic_endpoint_is_not_evidence():
    a, b = make(clues=["api:/api/v1/users/"]), make(clues=["api:/api/v1/users/"])
    assert not any("endpoint" in s for s in score(a, b)["strong_links"])


def test_technical_traces_missing_on_one_side_are_skipped_not_scored_zero():
    a, b = make(tracker="meta_pixel:111", clues=["POST x.test/api/v1/a/"]), make()
    r = score(a, b)
    assert "tracker_ids" in r["missing"] and "dom_and_form_clues" in r["missing"] and r["score"] > 0.95
    assert score(a, make(tracker="meta_pixel:222", clues=["POST y.test/api/v2/b/"]))["score"] < r["score"]  # both known, different


def test_supporting_feature_counts_a_match_but_drops_a_difference():
    from ads.sim_functions import compare_all
    a, b = make(product="AlphaPlat"), make(product="BetaPlat")
    plain = compare_all(a, b)["score"]
    sup = {"features": frozenset(["product_name"]), "min": 0.5}
    assert compare_all(a, b, supporting=sup)["score"] > plain                     # the different product no longer subtracts
    assert compare_all(a, make(), supporting=sup)["score"] == compare_all(a, make())["score"]  # a match counts as before


def test_tracking_template_is_family_evidence_and_an_ad_campaign_id_joins_a_campaign():
    from ads import clustering
    from ads.sim_functions.attributes import url_tokens
    own = "https://a.test/p?utm_source=fb&utm_medium=paid&utm_xyz=<value>"
    std = "https://b.test/p?utm_source=fb&utm_medium=paid&fbclid=<value>"
    ad = "https://c.test/p?utm_id=120200000000000001&utm_source=fb"
    assert url_tokens([own]) == ["params:utm_medium,utm_source,utm_xyz"] and url_tokens([std]) == []
    assert url_tokens([ad]) == ["adid:120200000000000001"]
    a, b = make(), make(product="Other", text="different words entirely here")
    a["technical_artifacts"]["redirect_chain"] = [own]
    b["technical_artifacts"]["redirect_chain"] = [own.replace("a.test", "z.test")]
    r = score(a, b)
    assert clustering.is_family_link(r) and not clustering.is_must_link(r) and r["contributions"]["url_template"] > 0
    a["technical_artifacts"]["redirect_chain"] = [ad]
    b["technical_artifacts"]["redirect_chain"] = [ad.replace("c.test", "y.test")]
    assert clustering.is_must_link(score(a, b))
