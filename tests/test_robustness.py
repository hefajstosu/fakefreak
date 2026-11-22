"""Tests for channel masks and the ablation metrics. Synthetic data only."""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import robustness as rb  # noqa: E402
from ads.similarity import score  # noqa: E402
from test_similarity import make  # noqa: E402

INFRA, TEXT, TEMPL, SCAM, ENT, PERS, PROPS = list(rb.GROUPS)


def test_each_mask_removes_only_its_own_group():
    p = make(tracker="meta_pixel:123", clues=["api:/api/v1/a/", "api:/api/v1/b/"])
    p["entities"]["product_or_platform"]["exact_name"] = "AlphaPlat"
    p["visual_and_production"]["ad_creative_template"] = "fake_news_report"
    p["core_narrative"]["persuasion_devices"] = ["countdown_timer"]
    infra = rb.mask_profile(p, [INFRA])
    assert infra["technical_artifacts"]["tracker_ids"] == [] and infra["entities"]["product_or_platform"]["exact_name"] == "AlphaPlat"
    assert rb.mask_profile(p, [ENT])["entities"]["product_or_platform"]["exact_name"] is None
    assert rb.mask_profile(p, [TEMPL])["visual_and_production"]["ad_creative_template"] is None
    assert rb.mask_profile(p, [PERS])["core_narrative"]["persuasion_devices"] == []
    assert rb.mask_profile(p, [SCAM])["core_narrative"]["ad_goal_scam_type"] == "other"
    assert rb.mask_profile(p, [TEXT])["canonical_comparison_text"] == ""
    assert p["technical_artifacts"]["tracker_ids"] == ["meta_pixel:123"]          # original untouched


def test_masking_infrastructure_removes_the_strong_link():
    a = make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor", tracker="meta_pixel:1")
    b = make(tracker="meta_pixel:1")
    assert score(a, b)["score"] >= 0.9
    assert score(rb.mask_profile(a, [INFRA]), rb.mask_profile(b, [INFRA]))["score"] < 0.5


def test_auc_counts_ties_as_half():
    assert rb._auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert rb._auc([0.5], [0.5]) == 0.5
    assert rb._auc([0.1], [0.9]) == 0.0


def test_metrics_on_a_tiny_synthetic_database():
    db = {"a": make(), "b": make(), "c": make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")}
    gold = {"case_ids": ["a", "b", "c"], "ranking_triples": [{"anchor": "a", "closer": "b", "farther": "c", "reason": ""}],
            "groups": [{"id": "g", "level": "same_campaign", "members": ["a", "b"]}]}
    m = rb.metrics(db, gold, 0.6)
    assert m["triples"] == "1/1" and m["auc"] == 1.0 and m["broad_precision"] == 1.0 and m["strict_recall"] == 1.0
