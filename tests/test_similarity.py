"""Tests for the placeholder similarity and clustering. Synthetic data only."""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import cluster as clu  # noqa: E402
from ads.similarity import score  # noqa: E402
from test_extract import profile  # noqa: E402


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


def test_cluster_groups_similar_and_leaves_outsider():
    db = {"a": make(), "b": make(), "c": make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")}
    groups = clu.cluster(db, 0.6)
    assert ["a", "b"] in groups and ["c"] in groups
    res = clu.assign(make(), db, 0.6)
    assert res["joins"] == [["a", "b"]] and not res["is_new_group"]
    assert clu.assign(make(scam="fake_online_casino", topic="gambling", product="Zed", text="slot spin bonus"), db, 0.6)["is_new_group"]


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
