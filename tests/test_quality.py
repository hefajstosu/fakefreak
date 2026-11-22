"""ads.evaluation.quality on synthetic profiles: outcomes of new material against known campaigns."""

from ads.evaluation import quality
from factory import OTHER, make


def test_quality_report_classifies_joins_misses_and_false_joins():
    db = {"a": make(), "b": make(product="Other", tracker="meta_pixel:1"), "c": make(**OTHER)}
    db["a"]["technical_artifacts"]["tracker_ids"] = ["meta_pixel:1"]
    gold = {"case_ids": ["a", "b", "c"], "groups": [{"level": "same_campaign", "members": ["a", "b"]}]}
    rows = {r["item"]: r for r in quality.leave_one_out(db, gold, 0.6)}
    assert rows["a"]["outcome"] == "correct" and rows["c"]["outcome"] == "correct" and rows["c"]["joined"] == []
    report = quality.run(0.6, db, gold, {"c": [make(**OTHER)]})
    assert report["variants, parent known, new infrastructure"]["accuracy"] == 1.0
    assert report["must-not-link (all items that should stay new)"]["stay_new_correct"] == 1.0
