"""preprocess/likeness.py without models or images: matching rule, source selection, clear error without models."""

import numpy as np
import pytest

from ads.preprocess import likeness as lk


def unit(v):
    v = np.array(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_best_match_is_the_highest_cosine_and_none_without_faces():
    a = np.stack([unit([1, 0, 0]), unit([0, 1, 0])])
    b = np.stack([unit([0.9, 0.1, 0]), unit([0, 0, 1])])
    assert abs(lk.best_match(a, b) - float(unit([1, 0, 0]) @ unit([0.9, 0.1, 0]))) < 1e-6
    assert lk.best_match(a, np.zeros((0, 3), dtype=np.float32)) is None


def test_sources_and_threshold():
    f = {"ad": np.ones((2, 128), np.float32), "page": np.ones((3, 128), np.float32)}
    assert len(lk.pick(f, "all")) == 5 and len(lk.pick(f, "ad")) == 2
    assert 0.3 < lk.SAME_PERSON < 0.4


def test_missing_models_give_a_clear_instruction(monkeypatch, tmp_path):
    monkeypatch.setattr(lk, "MODELS_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="--download"):
        lk._models()
