"""Tests for model failover and graceful degradation. No network."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ads.llm.client import QuotaExhausted, is_quota_error, with_fallback  # noqa: E402


def test_moves_to_next_model_when_quota_is_exhausted():
    calls = []

    def fn(m):
        calls.append(m)
        if m != "c":
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
        return "ok from " + m

    assert with_fallback(["a", "b", "c"], fn) == "ok from c" and calls == ["a", "b", "c"]


def test_raises_quota_exhausted_when_every_model_fails():
    def fn(m):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(QuotaExhausted) as e:
        with_fallback(["a", "b"], fn)
    assert "a, b" in str(e.value)


def test_other_errors_are_not_swallowed_by_failover():
    def fn(m):
        raise ValueError("bad request: schema")

    with pytest.raises(ValueError):
        with_fallback(["a", "b"], fn)


def test_unavailable_model_counts_as_failover_case():
    assert is_quota_error(RuntimeError("404 NOT_FOUND: model no longer available to new users"))
    assert not is_quota_error(RuntimeError("500 internal"))


def test_quota_exhausted_is_not_retried_by_the_client(monkeypatch, tmp_path):
    from ads.llm.client import LLMClient

    class C(LLMClient):
        n = 0

        def _call(self, system, parts):
            C.n += 1
            raise QuotaExhausted("all models exhausted")

    c = C("m", str(tmp_path), max_retries=3)
    with pytest.raises(QuotaExhausted):
        c.generate_text("s", [("text", "x")])
    assert C.n == 1                         # failed fast instead of sleeping and retrying
