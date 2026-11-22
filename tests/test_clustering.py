"""Tests for ads.clustering on synthetic data."""

from ads import clustering as cl
from factory import OTHER, make


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
    assert res["joins"] == [["a", "b"]]
    assert not cl.assign(make(scam="fake_online_casino", topic="gambling", product="Zed", text="slot spin bonus"), db, 0.6)["joins"]


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
    with_v = cl.pair_scores(db, variants)
    assert plain["via_variant"] is None and with_v[("a", "c")]["via_variant"] == "b:0"
    assert with_v[("a", "c")]["score"] > plain["score"]
    assert sorted(x for g in cl.cluster(db, 0.6, with_v) for x in g) == ["a", "c"]   # only real articles appear


def test_variants_are_never_compared_with_each_other(monkeypatch):
    from ads.clustering import pairs
    calls = []
    real = pairs.score
    monkeypatch.setattr(pairs, "score", lambda x, y: calls.append(1) or real(x, y))
    cl.best_score(make(), make(**OTHER), [make(), make()], [make(), make(), make()])
    assert len(calls) == 1 + 5          # the real pair, then 2 + 3 variants against the other real article


def test_near_identical_content_joins_alone_but_a_weaker_pair_needs_the_mean():
    ids = {k: {} for k in "abc"}
    s = fake({("a", "b"): 0.85, ("b", "c"): 0.85, ("a", "c"): 0.1})
    assert cl.cluster(ids, 0.6, s) == [["a", "b", "c"]]   # each pair is the same ad again: seeds, not averages
    assert cl.joins_alone({"score": 0.8, "strong_links": []}) and not cl.joins_alone({"score": 0.79, "strong_links": []})


def test_shared_platform_endpoints_make_a_family_not_a_campaign():
    clues = ["api:/api/v1/agent/persist-session-record/", "api:/api/v1/trigger/field/"]
    db = {"a": make(clues=clues), "b": make(product="Other", text="different words entirely here", clues=clues),
          "c": make(**OTHER, clues=clues)}
    s = cl.pair_scores(db)
    assert cl.is_family_link(s[("a", "b")]) and not cl.is_must_link(s[("a", "b")])
    camps = cl.cluster(db, 0.99, s)                       # no campaign at this tau
    fams = [sorted(c for i in f for c in camps[i]) for f in cl.hierarchy(db, camps, 0.99, s)]
    assert ["a", "b"] in fams and ["c"] in fams           # same tool and scam type: family; other scam type: apart
