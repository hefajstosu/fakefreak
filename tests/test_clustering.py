"""Tests for ads.clustering on synthetic data."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import clustering as cl  # noqa: E402
from test_similarity import make  # noqa: E402

OTHER = dict(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")


def fake(scores, links=None):
    links = links or {}
    return {k: {"score": v, "strong_links": links.get(k, [])} for k, v in scores.items()}


def test_average_link_does_not_chain_through_one_weak_bridge():
    ids = {k: {} for k in "abc"}
    s = fake({("a", "b"): 0.7, ("b", "c"): 0.7, ("a", "c"): 0.1})  # above tau, below the same-content score
    # single link would give one group; mean(a,c)=0.1 blocks the second merge only if c joins neither strongly
    groups = cl.cluster(ids, 0.6, s)
    assert sorted(len(g) for g in groups) == [1, 2]


def test_must_link_joins_low_scoring_pair():
    ids = {k: {} for k in "ab"}
    s = fake({("a", "b"): 0.2}, {("a", "b"): ["shared tracker ID: meta_pixel:1"]})
    assert cl.cluster(ids, 0.6, s) == [["a", "b"]]
    assert cl.cluster(ids, 0.6, s, use_must_link=False) == [["a"], ["b"]]


def test_shared_domain_alone_is_not_a_must_link():
    assert not cl.is_must_link({"strong_links": ["shared domain: example.test"]})


def test_cluster_and_assign_on_profiles():
    db = {"a": make(), "b": make(), "c": make(**OTHER)}
    assert cl.cluster(db, 0.6) == [["a", "b"], ["c"]]
    res = cl.assign(make(), db, 0.6)
    assert res["joins"] == [["a", "b"]] and not res["is_new_group"]
    assert cl.assign(make(scam="fake_online_casino", topic="gambling", product="Zed", text="slot spin bonus"), db, 0.6)["is_new_group"]


def test_hierarchy_links_same_scam_type_campaigns_only():
    db = {"a": make(), "b": make(product="Other", text="invest account broker"), "c": make(**OTHER)}
    campaigns = [["a"], ["b"], ["c"]]
    s = fake({("a", "b"): 0.45, ("a", "c"): 0.45, ("b", "c"): 0.45})
    fams = cl.hierarchy(db, campaigns, 0.3, s)
    assert [0, 1] in fams and [2] in fams


def test_variants_raise_scores_but_are_never_grouped():
    db = {"a": make(), "c": make(**OTHER)}
    variants = {"c": [make()]}          # a variant of c that looks like a
    plain = cl.pair_scores(db)[("a", "c")]
    with_v = cl.pair_scores(db, variants)[("a", "c")]
    assert plain["via_variant"] is None and with_v["via_variant"] == "b:0" and with_v["score"] > plain["score"]
    assert with_v["base"] == plain["base"]
    groups = cl.cluster(db, 0.6, variants=variants)
    assert sorted(x for g in groups for x in g) == ["a", "c"]       # only real articles appear
    res = cl.assign(make(), db, 0.6, variants=variants)
    assert all(c in db for c, _ in res["neighbours"]) and ["a", "c"] in res["joins"]


def test_gate_skips_variants_of_hopeless_pairs_but_keeps_close_or_evidenced_ones():
    a, far = make(), make(**OTHER)
    variants = {"far": [make(), make()]}
    st = {}
    r = cl.best_score(a, far, None, variants["far"], variant_gate=0.9, stats=st)      # direct score is below the gate
    assert r["via_variant"] is None and st == {"variant_comparisons_skipped": 2}
    st = {}
    r = cl.best_score(a, far, None, variants["far"], variant_gate=0.1, stats=st)      # passes the gate
    assert r["via_variant"] == "b:0" and st == {"variant_comparisons": 2}
    t1, t2 = make(tracker="meta_pixel:1"), make(tracker="meta_pixel:1", **OTHER)
    st = {}
    cl.best_score(t1, t2, None, [make()], variant_gate=0.99, stats=st)                # hard evidence bypasses the gate
    assert st == {"variant_comparisons": 1}


def test_variants_are_never_compared_with_each_other():
    a, b = make(), make(**OTHER)
    st = {}
    cl.best_score(a, b, [make(), make()], [make(), make(), make()], stats=st)
    assert st["variant_comparisons"] == 5           # 2 + 3, not 2 * 3 more


def test_near_identical_content_joins_alone_but_a_weaker_pair_needs_the_mean():
    ids = {k: {} for k in "abc"}
    s = fake({("a", "b"): 0.85, ("b", "c"): 0.85, ("a", "c"): 0.1})
    assert cl.cluster(ids, 0.6, s) == [["a", "b", "c"]]   # each pair is the same ad again: seeds, not averages
    assert cl.joins_alone({"score": 0.8, "strong_links": []}) and not cl.joins_alone({"score": 0.79, "strong_links": []})


def test_quality_report_classifies_joins_misses_and_false_joins():
    from ads import quality
    db = {"a": make(), "b": make(product="Other", tracker="meta_pixel:1"), "c": make(**OTHER)}
    db["a"]["technical_artifacts"]["tracker_ids"] = ["meta_pixel:1"]
    gold = {"case_ids": ["a", "b", "c"], "groups": [{"level": "same_campaign", "members": ["a", "b"]}]}
    rows = {r["item"]: r for r in quality.leave_one_out(db, gold, 0.6)}
    assert rows["a"]["outcome"] == "correct" and rows["c"]["outcome"] == "correct" and rows["c"]["joined"] == []
    report = quality.run(0.6, db, gold, {"c": [make(**OTHER)]})
    assert report["variants, parent known, new infrastructure"]["accuracy"] == 1.0
    assert report["must-not-link (all items that should stay new)"]["stay_new_correct"] == 1.0
