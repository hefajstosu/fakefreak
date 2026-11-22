"""config/cluster.yaml must actually drive the similarity weights."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads.sim_functions import ANCHOR_WEIGHTS, DEFAULT_WEIGHTS, compare_all, load_config  # noqa: E402
from test_similarity import make  # noqa: E402


def write(tmp_path, text):
    f = tmp_path / "c.yaml"
    f.write_text(text, encoding="utf-8")
    return str(f)


def test_repo_config_is_valid_and_matches_defaults_for_listed_keys():
    cfg = load_config()
    assert set(cfg["weights"]) == set(DEFAULT_WEIGHTS) | set(ANCHOR_WEIGHTS)
    assert cfg["weights"]["scam_type"] == 1.0 and cfg["weights"]["topic"] == DEFAULT_WEIGHTS["topic"]  # unlisted key keeps default


def test_weights_from_file_change_the_score(tmp_path):
    a, b = make(), make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")
    base = compare_all(a, b, weights=load_config()["weights"])["score"]
    heavy = load_config(write(tmp_path, "weights:\n  scam_type: 50.0\n"))
    assert compare_all(a, b, weights=heavy["weights"])["score"] < base   # scam type differs, now dominates


def test_unknown_or_negative_weight_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        load_config(write(tmp_path, "weights:\n  scam_typ: 1.0\n"))
    with pytest.raises(ValueError, match=">= 0"):
        load_config(write(tmp_path, "weights:\n  scam_type: -1\n"))


def test_ignore_values_are_never_anchor_evidence(tmp_path):
    a, b = make(clues=["file:x.js", "form:a"]), make(clues=["file:x.js", "form:b"])
    cfg = load_config(write(tmp_path, "ignore_values: ['file:x.js']\n"))
    plain = compare_all(a, b, anchor_stats={})["features"]["dom_and_form_clues"]["similarity"]
    ignored = compare_all(a, b, anchor_stats=cfg["anchor_stats"])["features"]["dom_and_form_clues"]["similarity"]
    assert plain > 0 and ignored == 0


def test_missing_file_means_defaults(tmp_path):
    assert load_config(str(tmp_path / "none.yaml"))["weights"]["scam_type"] == DEFAULT_WEIGHTS["scam_type"]
