"""Web panel: a small JSON API over ads/analyze.py plus the static page in ./static. Standard library only.

    cd src && python -m ads.web.server [--host 127.0.0.1] [--port 8000]      then open http://127.0.0.1:8000

API
  GET  /api/status                 {"cases": n, "llm": bool}
  GET  /api/groups?tau=0.6         {"tau", "groups": [{"no", "family", "scam_type", "members": [summary], "links": [...]}]}
  POST /api/analyze {url, text, tau}   {"id", "notes", "llm_used", "decision", "profile", "neighbours", "joins"}
  POST /api/save {id}              {"case_id"}
  GET  /api/image/<case_id>        first screenshot of a database case

It listens on 127.0.0.1 by default: the page shows organiser sample data, which must not be published. The container
listens on 0.0.0.0 inside and docker-compose.yml publishes the port on the host's 127.0.0.1 only.
"""
import argparse
import json
import mimetypes
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlsplit

from .. import analyze as an
from ..evaluate import case_meta, load_profiles
from ..llm.client import QuotaExhausted, load_env, make_client

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 200_000


class State:
    """Database profiles and pending analyses, shared by the request threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.client = None
        self.pending: Dict[str, Tuple[dict, dict]] = {}  # analysis id -> (case, result), until saved
        self.reload()

    def reload(self):
        self.profiles = load_profiles()
        self.groups: Dict[float, list] = {}

    def llm(self):
        with self.lock:
            if self.client is None:
                self.client = make_client()
            return self.client


def summary(cid: str, profile: dict) -> Dict[str, Any]:
    s = an.case_summary(cid, profile)
    s["image_url"] = f"/api/image/{cid}" if s.pop("image") else None
    s["unconfirmed"] = case_meta(cid).get("status") == "unconfirmed"
    return s


def parse_tau(value) -> float:
    tau = float(value)
    if not 0.05 <= tau <= 0.95:
        raise ValueError("tau must be between 0.05 and 0.95")
    return round(tau, 2)


def groups_payload(state: State, tau: float) -> Dict[str, Any]:
    with state.lock:
        if tau not in state.groups:
            state.groups[tau] = an.groups_overview(state.profiles, tau)
        groups = state.groups[tau]
    return {"tau": tau, "groups": [{"no": i, "family": g["family"], "scam_type": g["scam_type"], "links": g["links"],
                                    "members": [summary(c, state.profiles[c]) for c in g["members"]]}
                                   for i, g in enumerate(groups, 1)]}


def analyze_payload(state: State, body: dict) -> Dict[str, Any]:
    tau = parse_tau(body.get("tau", 0.6))
    case, notes = an.build_case(url=str(body.get("url") or ""), text=str(body.get("text") or ""))
    if case is None:
        raise ValueError("No article text: " + ("; ".join(notes) or "give a URL or paste the text") + ".")
    res = an.analyse(case, state.profiles, tau, state.llm())
    aid = uuid.uuid4().hex
    with state.lock:
        state.pending[aid] = (case, res)
    return {"id": aid, "notes": notes, "llm_used": res["llm_used"],
            "decision": {k: res["decision"][k] for k in ("status", "title", "explanation")},
            "profile": summary("new", res["profile"]), "joins": res["joins"],
            "neighbours": [{"case": c, "score": round(r["score"], 3), "evidence": r["strong_links"],
                            "product": an.case_summary(c, state.profiles[c])["product"]} for c, r in res["neighbours"]]}


def save_payload(state: State, body: dict) -> Dict[str, Any]:
    with state.lock:
        item = state.pending.pop(str(body.get("id")), None)
    if item is None:
        raise KeyError("This analysis is unknown or already saved; run it again.")
    case, res = item
    cid = an.save_case(case, res["profile"], res["decision"])
    with state.lock:
        state.reload()
    return {"case_id": cid}


def make_handler(state: State):
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
                return self.send_json(503, {"error": "All configured models are out of quota. Browsing the groups still works."})
            code = 400 if isinstance(e, (ValueError, json.JSONDecodeError)) else 404 if isinstance(e, KeyError) else 500
            self.send_json(code, {"error": str(e).strip("'\"")[:400]})

        def do_GET(self):
            parts = urlsplit(self.path)
            try:
                if parts.path == "/api/status":
                    return self.send_json(200, {"cases": len(state.profiles), "llm": bool(os.environ.get("GEMINI_API_KEY"))})
                if parts.path == "/api/groups":
                    return self.send_json(200, groups_payload(state, parse_tau(parse_qs(parts.query).get("tau", ["0.6"])[0])))
                if parts.path.startswith("/api/image/"):
                    cid = parts.path.rsplit("/", 1)[1]
                    path = an.first_image(cid) if cid in state.profiles else None  # only cases of the database
                    if not path:
                        return self.send_json(404, {"error": "no image"})
                    return self.send(200, open(path, "rb").read(), mimetypes.guess_type(path)[0] or "image/png")
                name = "index.html" if parts.path in ("/", "/index.html") else parts.path.lstrip("/")
                path = os.path.normpath(os.path.join(STATIC, name))
                if not path.startswith(STATIC + os.sep) or not os.path.isfile(path):
                    return self.send_json(404, {"error": "not found"})
                ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
                return self.send(200, open(path, "rb").read(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
            except Exception as e:  # noqa: BLE001
                self.fail(e)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    raise ValueError("request too large")
                body = json.loads(self.rfile.read(n) or b"{}")
                path = urlsplit(self.path).path
                if path == "/api/analyze":
                    return self.send_json(200, analyze_payload(state, body))
                if path == "/api/save":
                    return self.send_json(200, save_payload(state, body))
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
    server = ThreadingHTTPServer((a.host, a.port), make_handler(State()))
    print(f"Panel: http://{a.host}:{a.port}  (Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
