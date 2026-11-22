"""The panel: a small HTTP server (standard library only) over api.py, plus the static page in ./static.

    cd src && python -m ads.web.server [--host 127.0.0.1] [--port 8000]      then open http://127.0.0.1:8000

    GET  /api/status                  {"cases", "llm"}
    GET  /api/groups?tau=0.6          campaigns with family, members, links and explanation
    GET  /api/group_by?trait=topic    cases grouped by the value of one trait (plus the list of traits)
    GET  /api/graph?tau=0.6           cases, campaigns, families and the links between them
    GET  /api/explain?a=&b=&tau=      why two cases are linked; a=new&id=<analysis id> for the analysed article
    GET  /api/image/<case id>         first screenshot of a database case
    POST /api/analyze                 {url, text, tau} as JSON, or multipart/form-data with any number of "files"
    POST /api/save {id}               store the analysed article in the database

It listens on 127.0.0.1 by default: the page shows the organiser's sample data, which must not be published. The
container listens on 0.0.0.0 inside and docker-compose.yml publishes the port on the host's 127.0.0.1 only.
"""
import argparse
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .. import database
from ..llm.client import QuotaExhausted, load_env
from . import api, uploads

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 200_000  # a JSON request


def make_handler(state: api.State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # one short line per request
            sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

        def send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, code: int, data: Any):
            self.send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def fail(self, e: Exception):
            if isinstance(e, QuotaExhausted):
                return self.send_json(503, {"error": "All configured models are out of quota. Browsing still works."})
            code = 400 if isinstance(e, (ValueError, json.JSONDecodeError)) else 404 if isinstance(e, KeyError) else 500
            self.send_json(code, {"error": str(e).strip("'\"")[:400]})

        def static(self, path: str):
            name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
            f = os.path.normpath(os.path.join(STATIC, name))
            if not f.startswith(STATIC + os.sep) or not os.path.isfile(f):
                return self.send_json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
            if f.endswith(".js"):
                ctype = "text/javascript"  # some systems map .js to text/plain, which browsers refuse for modules
            self.send(200, open(f, "rb").read(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))

        def image(self, cid: str):
            path = database.first_image(cid) if cid in state.profiles else None  # only cases of the database
            if not path:
                return self.send_json(404, {"error": "no image"})
            self.send(200, open(path, "rb").read(), mimetypes.guess_type(path)[0] or "image/png")

        def do_GET(self):
            url = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/status":
                    return self.send_json(200, api.status(state))
                if url.path == "/api/groups":
                    return self.send_json(200, api.groups(state, api.parse_tau(q.get("tau", "0.6"))))
                if url.path == "/api/group_by":
                    return self.send_json(200, api.group_by(state, q.get("trait", "")))
                if url.path == "/api/graph":
                    return self.send_json(200, api.graph(state, api.parse_tau(q.get("tau", "0.6"))))
                if url.path == "/api/explain":
                    return self.send_json(200, api.explain_pair(state, q))
                if url.path.startswith("/api/image/"):
                    return self.image(url.path.rsplit("/", 1)[1])
                self.static(url.path)
            except Exception as e:  # noqa: BLE001 - every error becomes a JSON answer
                self.fail(e)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                ctype = self.headers.get("Content-Type") or ""
                path = urlsplit(self.path).path
                if ctype.startswith("multipart/form-data"):
                    if path != "/api/analyze":
                        raise ValueError("files can only be sent to /api/analyze")
                    if n > uploads.MAX_UPLOAD:
                        raise ValueError(f"request too large (limit {uploads.MAX_UPLOAD // 1_000_000} MB)")
                    fields, files = uploads.parse_multipart(ctype, self.rfile.read(n))
                    return self.send_json(200, api.analyze(state, fields, files))
                if n > MAX_BODY:
                    raise ValueError("request too large")
                body = json.loads(self.rfile.read(n) or b"{}")
                if path == "/api/analyze":
                    return self.send_json(200, api.analyze(state, body))
                if path == "/api/save":
                    return self.send_json(200, api.save(state, body))
                self.send_json(404, {"error": "not found"})
            except Exception as e:  # noqa: BLE001
                self.fail(e)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="Web panel for analysing articles against the known fake campaigns")
    ap.add_argument("--host", default=os.environ.get("ADS_HOST", "127.0.0.1"),
                    help="address to listen on (env ADS_HOST); 0.0.0.0 only inside a container or a private network")
    ap.add_argument("--port", type=int, default=int(os.environ.get("ADS_PORT", "8000")), help="env ADS_PORT")
    a = ap.parse_args()
    load_env()
    server = ThreadingHTTPServer((a.host, a.port), make_handler(api.State()))
    print(f"Panel: http://{a.host}:{a.port}  (Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
