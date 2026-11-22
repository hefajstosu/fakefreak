"""Tests for the web panel's API. Synthetic data only: no network, no LLM, nothing read from or written to data/."""
import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from ads import database, dedup
from ads.llm.client import MockClient
from ads.web import api, uploads
from ads.web import server as srv
from factory import make


@pytest.fixture
def panel(monkeypatch, tmp_path):
    state = api.State.__new__(api.State)  # skip reload(): no profiles from disk
    state.lock, state.pending, state.groups = threading.Lock(), {}, {}
    state.profiles = {"a": make(product="AlphaPlat", tracker="meta_pixel:111"), "b": make(product="AlphaPlat"),
                      "c": make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")}
    state.client = MockClient([json.dumps(make(product="AlphaPlat"))])
    state.reload = lambda: state.groups.clear()
    monkeypatch.setattr(dedup, "load_fingerprints", lambda: {})
    monkeypatch.setattr(database, "first_image", lambda cid: None)
    monkeypatch.setattr(database, "case_meta", lambda cid: {})
    real_save = database.save_case
    monkeypatch.setattr(database, "save_case", lambda case, p, d: real_save(case, p, d, cases_dir=str(tmp_path)))
    server = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    server.shutdown()


def call(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_page_and_static_files_are_served_but_nothing_outside(panel):
    base, _ = panel
    code, body = call(base + "/")
    assert code == 200 and b"Panel analizy" in body
    assert call(base + "/js/main.js")[0] == 200 and call(base + "/js/../index.html")[0] == 200
    assert call(base + "/../server.py")[0] == 404
    assert call(base + "/api/image/zzz")[0] == 404


def test_groups_endpoint_lists_campaigns_with_members(panel):
    base, _ = panel
    code, body = call(base + "/api/groups?tau=0.6")
    data = json.loads(body)
    assert code == 200 and data["tau"] == 0.6
    members = [[m["case"] for m in g["members"]] for g in data["groups"]]
    assert ["c"] in members and all(m["image_url"] is None for g in data["groups"] for m in g["members"])
    assert call(base + "/api/groups?tau=7")[0] == 400


def test_analyse_then_save(panel):
    base, tmp = panel
    assert call(base + "/api/analyze", {"url": "", "text": ""})[0] == 400
    code, body = call(base + "/api/analyze", {"url": "", "text": "Inwestuj w AlphaPlat.", "tau": 0.6})
    r = json.loads(body)
    assert code == 200 and r["llm_used"] and r["neighbours"][0]["case"] in ("a", "b")
    assert r["decision"]["status"] in ("confirmed", "likely") and r["profile"]["product"] == "AlphaPlat"
    code, body = call(base + "/api/save", {"id": r["id"]})
    assert code == 200 and json.loads(body)["case_id"] == "web_1" and (tmp / "web_1" / "profile.json").exists()
    assert call(base + "/api/save", {"id": r["id"]})[0] == 404  # saved once only


def test_explanations_in_analysis_groups_and_explain_endpoint(panel):
    base, _ = panel
    r = json.loads(call(base + "/api/analyze", {"url": "", "text": "Inwestuj w AlphaPlat.", "tau": 0.6})[1])
    assert r["reasons"]["rule"] and r["thresholds"]["tau"] == 0.6
    assert any(c["joined"] for c in r["campaigns"]) and all(c["no"] for c in r["campaigns"])
    ex = r["neighbours"][0]["explanation"]
    assert abs(sum(g["contribution"] for g in ex["groups"]) - ex["score"]) < 0.01
    code, body = call(base + f"/api/explain?a=new&b=c&id={r['id']}&tau=0.6")
    assert code == 200 and json.loads(body)["b"] == "c"
    code, body = call(base + "/api/explain?a=a&b=b")
    assert code == 200 and json.loads(body)["must_link"] is False
    assert call(base + "/api/explain?a=a&b=zzz")[0] == 404
    assert call(base + "/api/explain?a=new&b=a&id=nope")[0] == 404
    groups = json.loads(call(base + "/api/groups?tau=0.6")[1])["groups"]
    assert all(g["explanation"]["rule"] for g in groups)


def test_graph_lists_cases_campaigns_and_links(panel):
    base, _ = panel
    g = json.loads(call(base + "/api/graph?tau=0.6")[1])
    assert sorted(n["case"] for n in g["nodes"]) == ["a", "b", "c"]
    camp = {n["case"]: n["campaign"] for n in g["nodes"]}
    assert camp["a"] == camp["b"] != camp["c"]
    ab = next(e for e in g["edges"] if (e["a"], e["b"]) == ("a", "b"))
    assert ab["same_campaign"] and not ab["must_link"]


def multipart(fields, files):
    boundary = "----testboundary7MA4YWxkTrZu0gW"
    out = b""
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    for name, data in files:
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{name}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def test_analyse_uploaded_files_then_save(panel, monkeypatch, tmp_path):
    import io
    from PIL import Image
    from ads.preprocess import domain_meta
    base, cases = panel
    monkeypatch.setattr(uploads, "UPLOADS", str(tmp_path / "uploads"))
    monkeypatch.setattr(domain_meta, "case_metadata", lambda *a, **k: [])   # no network in tests
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "red").save(buf, format="PNG")
    page = b"<html><body><h1>Inwestuj w AlphaPlat</h1><p>" + b"Zarabiaj codziennie. " * 30 + b"</p></body></html>"
    body, ctype = multipart({"tau": "0.6", "url": "", "text": ""},
                            [("../../ad shot.png", buf.getvalue()), ("article.html", page), ("notes.exe", b"MZ")])
    req = urllib.request.Request(base + "/api/analyze", data=body, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req) as r:
        res = json.loads(r.read())
    assert res["profile"]["product"] == "AlphaPlat" and any("notes.exe" in n for n in res["notes"])
    stored = os.listdir(tmp_path / "uploads" / res["id"])
    assert "ad_shot.png" in stored and "article.html" in stored and not any("/" in n for n in stored)
    assert call(base + "/api/save", {"id": res["id"]})[0] == 200
    assert not (tmp_path / "uploads" / res["id"]).exists()                  # cleaned up once saved
    assert any(f.endswith(".png") for f in os.listdir(cases / "web_1"))     # the screenshot went with the case


def test_upload_with_nothing_usable_is_a_clear_400(panel, monkeypatch, tmp_path):
    base, _ = panel
    monkeypatch.setattr(uploads, "UPLOADS", str(tmp_path / "uploads"))
    body, ctype = multipart({"tau": "0.6"}, [("virus.exe", b"MZ")])
    req = urllib.request.Request(base + "/api/analyze", data=body, headers={"Content-Type": ctype})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 400 and b"Nothing to analyse" in e.value.read()
    assert not os.listdir(tmp_path / "uploads")                              # failed analysis leaves no files


def test_safe_names_stay_inside_and_do_not_collide():
    used = set()
    assert uploads.safe_name("../../etc/passwd", used) == "passwd"
    assert uploads.safe_name("C:\\x\\shot one.png", used) == "shot_one.png"
    assert uploads.safe_name("shot one.png", used) == "shot_one_2.png"
    assert uploads.safe_name(".hidden", used) == "hidden"


def test_group_by_trait_groups_cases_with_the_same_value(panel):
    base, _ = panel
    code, body = call(base + "/api/group_by?trait=product")
    assert code == 200
    data = json.loads(body)
    assert [g["value"] for g in data["groups"]] == ["AlphaPlat", "PillX"]
    assert [[m["case"] for m in g["members"]] for g in data["groups"]] == [["a", "b"], ["c"]]
    assert "scam_type" in [t["key"] for t in data["traits"]]


def test_group_by_without_trait_lists_traits_and_unknown_trait_is_an_error(panel):
    base, _ = panel
    assert json.loads(call(base + "/api/group_by?trait=")[1])["groups"] == []
    assert call(base + "/api/group_by?trait=nonsense")[0] == 400


def test_group_by_trait_merges_spellings_and_keeps_cases_without_a_value():
    from ads.web import traits
    a, b, c = make(product="TVN24"), make(product="tvn24"), make(product=None)
    c["entities"]["product_or_platform"]["generic_category"] = None
    groups = traits.group_by({"1": a, "2": b, "3": c}, "product")
    assert groups == [{"value": "TVN24", "members": ["1", "2"]}, {"value": None, "members": ["3"]}]
    c["entities"]["featured_people"] = [{"name": "Ann"}, {"name": "ann"}]
    assert traits.group_by({"3": c}, "people") == [{"value": "Ann", "members": ["3"]}]
