"""Tests for the web panel's API. Synthetic data only: no network, no LLM, nothing read from or written to data/."""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

from ads import analyze as an  # noqa: E402
from ads.llm.client import MockClient  # noqa: E402
from ads.web import server as srv  # noqa: E402
from test_similarity import make  # noqa: E402


@pytest.fixture
def panel(monkeypatch, tmp_path):
    state = srv.State.__new__(srv.State)  # skip reload(): no profiles from disk
    state.lock, state.pending, state.groups = threading.Lock(), {}, {}
    state.profiles = {"a": make(product="AlphaPlat", tracker="meta_pixel:111"), "b": make(product="AlphaPlat"),
                      "c": make(scam="miracle_cure", topic="health", product="PillX", text="cure capsule doctor")}
    state.client = MockClient([json.dumps(make(product="AlphaPlat"))])
    state.reload = lambda: state.groups.clear()
    monkeypatch.setattr(an.dedup, "load_fingerprints", lambda: {})
    monkeypatch.setattr(an, "first_image", lambda cid: None)
    monkeypatch.setattr(srv, "case_meta", lambda cid: {})
    real_save = an.save_case
    monkeypatch.setattr(an, "save_case", lambda case, p, d: real_save(case, p, d, cases_dir=str(tmp_path)))
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
    assert call(base + "/app.js")[0] == 200
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
