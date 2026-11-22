"""ads.features on synthetic profiles: the per-feature report must separate a linked pair from unrelated ones."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import features  # noqa: E402
from test_similarity import make  # noqa: E402

OTHER = dict(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")


def test_feature_table_measures_coverage_auc_and_false_hits():
    db = {"a": make(tracker="meta_pixel:1"), "b": make(tracker="meta_pixel:1"), "c": make(**OTHER),
          "d": make(scam="fake_online_casino", topic="gambling", product="Zed", text="slot spin bonus")}
    gold = {"case_ids": list(db), "groups": [{"level": "same_campaign", "members": ["a", "b"]}]}
    rows = {r["feature"]: r for r in features.feature_table(db, gold)}
    assert rows["scam_type"]["auc"] == 1.0 and rows["scam_type"]["coverage"] == 1.0
    assert rows["tracker_ids"]["coverage"] == 0.5 and rows["tracker_ids"]["comparable"] == 1 / 6
    assert rows["product_name"]["strict"] == 1.0 and rows["product_name"]["false_hits"] == 0
    assert "| scam_type |" in features.markdown(list(rows.values()), 4)
