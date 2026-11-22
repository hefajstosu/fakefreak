"""Tests for ads.explain on synthetic profiles: the explanation must add up to the score and name real values."""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import clustering, explain  # noqa: E402
from ads.similarity import score  # noqa: E402
from test_similarity import make  # noqa: E402

OTHER = dict(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")


def test_pair_contributions_add_up_to_the_score():
    a, b = make(tracker="meta_pixel:111"), make(product="BetaPlat", tracker="meta_pixel:111")
    ex = explain.pair(a, b, tau=0.6)
    assert ex["score"] == score(a, b)["score"]
    assert abs(sum(f["contribution"] for f in ex["features"] if f["contribution"] is not None) - ex["score"]) < 0.01
    assert abs(sum(g["contribution"] for g in ex["groups"]) - ex["score"]) < 0.01


def test_pair_names_shared_and_differing_values_and_hard_evidence():
    a, b = make(tracker="meta_pixel:111"), make(product="BetaPlat", tracker="meta_pixel:111")
    ex = explain.pair(a, b)
    feats = {f["feature"]: f for f in ex["features"]}
    assert feats["tracker_ids"]["values"]["shared"][0]["a"] == "meta_pixel:111"
    assert feats["product_name"]["values"] == {"a": "AlphaPlat", "b": "BetaPlat"} and feats["product_name"]["loss"] > 0
    assert ex["must_link"] and ex["evidence"][0]["kind"] == "tracker" and ex["evidence"][0]["value"] == "meta_pixel:111"


def test_missing_data_is_reported_per_side_not_counted():
    a, b = make(), make()
    a["visual_and_production"]["landing_page_template"] = None
    b["visual_and_production"]["landing_page_template"] = "fake_news_article"
    feats = {f["feature"]: f for f in explain.pair(a, b)["features"]}
    assert feats["landing_page_template"]["missing"] == "a" and feats["landing_page_template"]["contribution"] is None


def test_without_a_group_matches_masking_that_group():
    a, b = make(tracker="meta_pixel:111"), make(**OTHER, tracker="meta_pixel:111")
    ex = explain.pair(a, b, tau=0.3)
    infra = next(g for g in ex["groups"] if g["group"] == "infrastructure")
    masked_a, masked_b = copy.deepcopy(a), copy.deepcopy(b)
    for p in (masked_a, masked_b):
        p["technical_artifacts"]["tracker_ids"] = []
    assert abs(infra["without"] - score(masked_a, masked_b)["score"]) < 0.01
    assert infra["without"] < ex["score"]


def test_campaign_signature_rule_and_nearest_other():
    db = {"a": make(tracker="meta_pixel:1"), "b": make(product="Other", tracker="meta_pixel:1"), "c": make(**OTHER)}
    scores = clustering.pair_scores(db)
    groups = clustering.cluster(db, 0.6, scores)
    ex = explain.campaign(["a", "b"], db, scores, 0.6, groups)
    assert ex["rule"] == "hard evidence" and ex["parts"] == [["a", "b"]]
    assert {"feature": "tracker_ids", "value": "meta_pixel:1"}.items() <= next(
        s for s in ex["signature"] if s["feature"] == "tracker_ids").items()
    assert ex["nearest"]["members"] == ["c"] and ex["nearest"]["gap"] > 0 and not ex["nearest"]["hard_evidence"]
    assert explain.campaign(["c"], db, scores, 0.6, groups)["rule"] == "single case"


def test_assignment_says_why_each_campaign_was_joined_or_not():
    db = {"a": make(), "b": make(), "c": make(**OTHER, tracker="meta_pixel:9")}
    res = clustering.assign(make(product="Zed", tracker="meta_pixel:9"), db, 0.6)
    rows = {tuple(r["members"]): r for r in explain.assignment(res, 0.6)}
    assert rows[("c",)]["joined"] and rows[("c",)]["rule"] == "hard evidence"
    assert rows[("c",)]["hard"][0]["evidence"][0]["value"] == "meta_pixel:9"
