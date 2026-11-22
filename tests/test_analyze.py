"""Tests for the panel's analysis module. Synthetic data only; no network (MockClient, no URL fetched)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import analyze as an  # noqa: E402
from ads.llm.client import MockClient  # noqa: E402
from test_similarity import make  # noqa: E402

DB = {
    "a": make(product="AlphaPlat", tracker="meta_pixel:111"),
    "b": make(product="AlphaPlat", text="invest platform deposit bonus"),
    "c": make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor"),
}


def test_build_case_from_pasted_text_only():
    case, notes = an.build_case(text="Artykuł o inwestycji w platformę.")
    assert case["parts"][0]["text"] == "Artykuł o inwestycji w platformę."
    assert case["parts"][0]["role"] == "bridge_page" and notes == []
    assert an.build_case(text="   ") == (None, [])


def test_build_case_roles_for_screenshots_pages_and_text(tmp_path):
    page = tmp_path / "p.html"
    page.write_text("<html><body><p>Artykuł o platformie.</p></body></html>", encoding="utf-8")
    case, _ = an.build_case(text="Formularz", images=["ad.png"], html_files=[str(page)], product="AlphaPlat",
                            text_role="offer_page")
    assert [p["role"] for p in case["parts"]] == ["ad_creative", "bridge_page", "offer_page"]
    assert case["parts"][0]["images"] == ["ad.png"] and "Artykuł o platformie" in case["parts"][1]["text"]
    assert case["parts"][2]["text"].startswith("Product or platform named by the analyst: AlphaPlat")


def test_compare_needs_no_llm_and_reports_capture_duplicates():
    fp = {"images": [], "texts": [], "urls": ["https://example.test/landing"]}
    r = an.compare(DB["a"], fp, {k: v for k, v in DB.items() if k != "a"}, 0.6,
                   fingerprints={"b": fp, "c": {"images": [], "texts": [], "urls": []}})
    assert r["decision"]["status"] == "duplicate" and r["duplicates"][0]["case"] == "b"
    assert an.compare(DB["a"], None, DB, 0.6, fingerprints={})["duplicates"] == []


def test_analyse_places_article_in_the_matching_campaign():
    case, _ = an.build_case(text="Inwestuj w AlphaPlat, wpłać depozyt.")
    client = MockClient([json.dumps(make(product="AlphaPlat"))])
    r = an.analyse(case, DB, 0.6, client, fingerprints={})
    assert r["llm_used"] and len(client.calls) == 1
    assert r["neighbours"][0][0] in ("a", "b") and r["neighbours"][-1][0] == "c"
    assert any(set(g) <= {"a", "b"} for g in r["joins"])
    assert r["decision"]["status"] in ("confirmed", "likely")


def test_repeat_capture_reuses_stored_profile_without_llm():
    case, _ = an.build_case(text="Inwestuj w AlphaPlat.")
    case["technical_summary"]["redirect_chain"] = ["https://example.test/landing"]
    fps = {"a": {"images": [], "texts": [], "urls": ["https://example.test/landing"]}}
    client = MockClient([])  # any LLM call would fail: no canned response
    r = an.analyse(case, DB, 0.6, client, fingerprints=fps)
    assert not r["llm_used"] and r["profile"] is DB["a"] and r["decision"]["status"] == "duplicate"


def test_groups_overview_separates_scam_types_and_lists_evidence():
    groups = an.groups_overview(DB, 0.6)
    assert {tuple(g["members"]) for g in groups} >= {("c",)}
    ab = next(g for g in groups if "a" in g["members"])
    assert "c" not in ab["members"] and ab["scam_type"] == "fake_investment"
    assert all({"a", "b", "score", "evidence"} <= set(link) for link in ab["links"])


def test_save_case_writes_profile_and_unconfirmed_status(tmp_path):
    case, _ = an.build_case(text="tekst")
    cid = an.save_case(case, DB["a"], {"status": "new_unconfirmed"}, cases_dir=str(tmp_path))
    assert cid == "web_1" and an.save_case(case, DB["a"], None, cases_dir=str(tmp_path)) == "web_2"
    meta = json.load(open(tmp_path / "web_1" / "meta.json", encoding="utf-8"))
    assert meta == {"decision": "new_unconfirmed", "status": "unconfirmed"}
    assert json.load(open(tmp_path / "web_1" / "case_input.json", encoding="utf-8"))["case_id"] == "web_1"


def test_case_summary_flattens_profile():
    s = an.case_summary("a", DB["a"])
    assert s["product"] == "AlphaPlat" and s["scam_type"] == "fake_investment" and s["trackers"] == ["meta_pixel:111"]
