"""ads.analysis (and the database it writes to) on synthetic data: no network, no LLM (MockClient)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from ads import analysis as an, database  # noqa: E402
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
    case, _ = an.build_case(text="Formularz", images=["ad.png"], html_files=[str(page)])
    assert [p["role"] for p in case["parts"]] == ["ad_creative", "bridge_page", "bridge_page"]
    assert case["parts"][0]["images"] == ["ad.png"] and "Artykuł o platformie" in case["parts"][1]["text"]
    assert case["parts"][2]["text"] == "Formularz"


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
    cid = database.save_case(case, DB["a"], {"status": "new_unconfirmed"}, cases_dir=str(tmp_path))
    assert cid == "web_1" and database.save_case(case, DB["a"], None, cases_dir=str(tmp_path)) == "web_2"
    meta = json.load(open(tmp_path / "web_1" / "meta.json", encoding="utf-8"))
    assert meta == {"decision": "new_unconfirmed", "status": "unconfirmed"}
    assert json.load(open(tmp_path / "web_1" / "case_input.json", encoding="utf-8"))["case_id"] == "web_1"


def test_case_summary_flattens_profile():
    s = an.case_summary("a", DB["a"])
    assert s["product"] == "AlphaPlat" and s["scam_type"] == "fake_investment" and s["trackers"] == ["meta_pixel:111"]


def test_pair_table_matches_pair_scores_and_compares_each_pair_once(monkeypatch):
    from ads import clustering
    from ads.analysis import index
    an.reset()
    full = clustering.pair_scores(DB)
    table = an.pair_table(DB)
    assert table.keys() == full.keys()
    assert all(table[k]["score"] == full[k]["score"] and table[k]["strong_links"] == full[k]["strong_links"]
               for k in full)
    calls = []
    real = index.score
    monkeypatch.setattr(index, "score", lambda *a: calls.append(1) or real(*a))
    an.pair_table(DB)
    assert calls == []                          # every pair is remembered
    an.pair_table({**DB, "d": make(product="Other")})
    assert len(calls) == 3                      # one new case: only its 3 pairs are scored


def test_campaigns_are_clustered_once_per_database_state(monkeypatch):
    from ads import clustering
    an.reset()
    calls = []
    real = clustering.cluster
    monkeypatch.setattr(clustering, "cluster", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = an.compare(make(), None, DB, 0.6, fingerprints={})
    assert an.compare(make(), None, DB, 0.6, fingerprints={})["joins"] == first["joins"] and len(calls) == 1
    an.compare(make(), None, {**DB, "d": make(product="Other")}, 0.6, fingerprints={})
    an.compare(make(), None, DB, 0.5, fingerprints={})
    assert len(calls) == 3                      # a saved case or another threshold clusters again


def test_compare_explains_the_decision_and_every_campaign():
    an.reset()
    r = an.compare(make(product="AlphaPlat"), None, DB, 0.6, fingerprints={})
    assert r["reasons"]["status"] == r["decision"]["status"] and r["reasons"]["thresholds"]["tau"] == 0.6
    rows = {tuple(c["members"]): c for c in r["campaigns"]}
    assert rows[("a", "b")]["joined"] and rows[("a", "b")]["rule"] == "same content"  # near-identical synthetic profiles
    assert not rows[("c",)]["joined"] and rows[("c",)]["gap"] > 0
    g = {tuple(x["members"]): x["explanation"] for x in an.groups_overview(DB, 0.6)}
    assert g[("a", "b")]["rule"] == "same content" and g[("c",)]["nearest"]["members"] == ["a", "b"]


def test_build_case_from_html_har_and_text_files_without_touching_the_template(tmp_path, monkeypatch):
    from ads.preprocess import domain_meta
    monkeypatch.setattr(domain_meta, "case_metadata", lambda *a, **k: ["registered:2026-01-01"])
    page = tmp_path / "a.html"
    page.write_text("<html><body><main><h1>Platforma</h1><p>" + "Zysk bez ryzyka. " * 30 + "</p></main></body></html>",
                    encoding="utf-8")
    note = tmp_path / "n.txt"
    note.write_text("Tekst artykułu z pliku.", encoding="utf-8")
    har = {"log": {"entries": [
        {"startedDateTime": "2026-01-02T10:00:00Z", "request": {"method": "GET", "url": "https://land.test/p?utm_xyz=1"},
         "response": {"status": 200, "headers": [], "content": {"mimeType": "text/html",
                                                                "text": "<html><body><p>" + "Kup teraz. " * 40 + "</p></body></html>"}}},
        {"startedDateTime": "2026-01-02T10:00:01Z", "request": {"method": "GET",
                                                                 "url": "https://connect.facebook.net/tr?id=123456789012345"},
         "response": {"status": 200, "headers": [], "content": {"mimeType": "image/gif"}}}]}}
    hf = tmp_path / "log.har"
    hf.write_text(json.dumps(har), encoding="utf-8")
    case, notes = an.build_case(html_files=[str(page)], hars=[str(hf)], text_files=[str(note)])
    roles = [p["role"] for p in case["parts"]]
    assert roles == ["bridge_page", "bridge_page"] and "Tekst artykułu" in case["parts"][1]["text"]
    t = case["technical_summary"]
    assert t["urls_and_domains"] and t["domain_and_cert_metadata"] == ["registered:2026-01-01"]
    assert t["page_fingerprints"]["structure"] and an.EMPTY_TECH["urls_and_domains"] == []
    alone, _ = an.build_case(hars=[str(hf)])                      # a log alone: its page text is read
    assert alone["parts"][0]["text"].startswith("Kup teraz")
    assert an.classify_files(["a.PNG", "b.har", "c.exe"]) == {"image": ["a.PNG"], "har": ["b.har"], "unsupported": ["c.exe"]}
