"""Tests for the live URL scanner against a local fake site (no real network)."""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ads.preprocess import url_scan as us  # noqa: E402

LONG_TEXT = "Fake article text about an investment platform. " * 12
FINAL = f"""<html><head><title>  Big   News </title>
<link rel="stylesheet" href="/static/site.css?v=3">
<script src="/static/app.7f3a.js"></script>
<script src="https://cdn.jsdelivr.net/npm/lib@1/lib.js"></script>
<script>fbq('init', '1234567890123'); gtag('config', 'G-ABCDEF1234'); gtag('config', 'AW-1112223334');</script>
<script async src="https://www.googletagmanager.com/gtm.js?id=GTM-ABCD123"></script></head>
<body><p>{LONG_TEXT}</p>
<form method="post" action="/send"><input name="fullname"><input name="phone"><select name="country"></select></form>
</body></html>"""


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body="", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        path = self.path.split("?")[0]
        if path == "/start":
            self._send(302, headers={"Location": "/mid?utm_id=ABC123&clickid=zzz"})
        elif path == "/mid":
            self._send(200, f'<html><head><meta http-equiv="refresh" content="0; url={base}/final"></head></html>')
        elif path == "/stub":
            self._send(200, f'<html><body><script>window.location.href = "{base}/final";</script></body></html>')
        elif path == "/loop":
            self._send(302, headers={"Location": "/loop"})
        elif path == "/final":
            self._send(200, FINAL)
        else:
            self._send(404, "nope")


@pytest.fixture(scope="module")
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_refuses_private_addresses_by_default(base):
    r = us.scan_url(base + "/final")
    assert not r["ok"] and "non-public" in r["error"]


def test_refuses_non_http_schemes():
    assert not us.scan_url("file:///etc/passwd")["ok"]
    assert not us.scan_url("ftp://example.com/x")["ok"]


def test_follows_http_and_meta_refresh_and_records_chain(base):
    r = us.scan_url(base + "/start", allow_private=True)
    assert r["ok"] and r["final_url"].endswith("/final")
    chain = r["technical_summary"]["redirect_chain"]
    assert len(chain) == 3  # /start -> /mid -> /final
    assert any("utm_id=ABC123" in c for c in chain)          # utm values kept
    assert not any("zzz" in c for c in chain)                # click IDs are not kept
    assert r["title"] == "Big News"


def test_extracts_trackers_forms_and_first_party_files(base):
    r = us.scan_url(base + "/final", allow_private=True)
    t = r["technical_summary"]
    assert "meta_pixel:1234567890123" in t["tracker_ids"]
    assert "google_tag_manager:GTM-ABCD123" in t["tracker_ids"]
    assert "google_tag:G-ABCDEF1234" in t["tracker_ids"] and "google_tag:AW-1112223334" in t["tracker_ids"]
    forms = [c for c in t["dom_and_form_clues"] if c.startswith("POST ")]
    assert forms and forms[0].endswith("/send fields=country,fullname,phone")
    files = [c for c in t["dom_and_form_clues"] if c.startswith("file:")]
    assert "file:app.7f3a.js" in files and "file:site.css" in files
    assert not any("lib.js" in f for f in files)             # third-party CDN is not a first-party trace
    assert "Fake article text" in r["text"]


def test_follows_js_redirect_stub_only_for_near_empty_pages(base):
    r = us.scan_url(base + "/stub", allow_private=True)
    assert r["ok"] and r["final_url"].endswith("/final")
    assert any("redirect" in n for n in r["notes"])


def test_redirect_loop_is_bounded(base):
    r = us.scan_url(base + "/loop", allow_private=True)
    assert r["ok"] and any("stopped after" in n for n in r["notes"])   # returns instead of hanging
    assert len(r["technical_summary"]["redirect_chain"]) <= us.MAX_HOPS


def test_unreachable_host_returns_error_not_exception():
    r = us.scan_url("http://127.0.0.1:9/x", allow_private=True)
    assert r["ok"] is False and "failed" in r["error"]
