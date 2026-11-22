"""Web panel: a small JSON API over ads/analyze.py plus the static page in ./static. Standard library only.

    cd src && python -m ads.web.server [--host 127.0.0.1] [--port 8000]      then open http://127.0.0.1:8000

API
  GET  /api/status                 {"cases": n, "llm": bool}
  GET  /api/groups?tau=0.6         {"tau", "groups": [{"no", "family", "scam_type", "members": [summary], "links": [...],
                                    "explanation": explain.campaign()}]}
  POST /api/analyze {url, text, tau}   {"id", "notes", "llm_used", "decision", "reasons", "campaigns", "profile",
                                    "neighbours": [{..., "explanation": explain.pair()}], "joins", "thresholds"}
  POST /api/save {id}              {"case_id"}
  GET  /api/explain?a=&b=&tau=     explain.pair() of two database cases; a=new&id=<analysis id> for the analysed article
  GET  /api/graph?tau=0.6          {"nodes": [...], "edges": [...]}: cases, campaigns, families and the links between them
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
from .. import decision, explain
from ..evaluate import case_meta, load_profiles
from ..llm.client import QuotaExhausted, load_env, make_client

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 200_000
MAX_PENDING = 50    # unsaved analyses kept in memory (oldest dropped first)
GRAPH_EDGES_PER_CASE = 4  # weaker links than these per case are left out of the graph (hard evidence always stays)


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


def overview(state: State, tau: float) -> list:
    with state.lock:
        if tau not in state.groups:
            state.groups[tau] = an.groups_overview(state.profiles, tau)
        return state.groups[tau]


def groups_payload(state: State, tau: float) -> Dict[str, Any]:
    return {"tau": tau, "groups": [{"no": i, "family": g["family"], "scam_type": g["scam_type"], "links": g["links"],
                                    "explanation": g["explanation"],
                                    "members": [summary(c, state.profiles[c]) for c in g["members"]]}
                                   for i, g in enumerate(overview(state, tau), 1)]}


def campaign_numbers(state: State, tau: float) -> Dict[frozenset, int]:
    """{members: K number shown in the groups tab}."""
    return {frozenset(g["members"]): i for i, g in enumerate(overview(state, tau), 1)}


def graph_payload(state: State, tau: float) -> Dict[str, Any]:
    """Cases as nodes (with campaign and family), links as edges: every pair with hard evidence, plus each case's
    strongest links at or above the family threshold (at most GRAPH_EDGES_PER_CASE per case)."""
    groups = overview(state, tau)
    where = {c: (i, g["family"]) for i, g in enumerate(groups, 1) for c in g["members"]}
    nodes = [{"case": c, "campaign": where[c][0], "family": where[c][1], **{k: an.case_summary(c, p)[k]
             for k in ("scam_type", "product")}} for c, p in sorted(state.profiles.items())]
    table = an.pair_table(state.profiles)
    keep = {k for k, r in table.items() if r["strong_links"]}
    near: Dict[str, list] = {}
    for k, r in table.items():
        if r["score"] >= decision.FAMILY_SCORE:
            for c in k:
                near.setdefault(c, []).append((r["score"], k))
    for links in near.values():
        keep |= {k for _, k in sorted(links, reverse=True)[:GRAPH_EDGES_PER_CASE]}
    edges = [{"a": a, "b": b, "score": table[(a, b)]["score"], "evidence": table[(a, b)]["strong_links"],
              "must_link": an.clustering.is_must_link(table[(a, b)]), "same_campaign": where[a][0] == where[b][0]}
             for a, b in sorted(keep)]
    return {"tau": tau, "family_score": decision.FAMILY_SCORE, "nodes": nodes, "edges": edges}


def explain_payload(state: State, query: Dict[str, list]) -> Dict[str, Any]:
    q = {k: v[0] for k, v in query.items()}
    tau = parse_tau(q.get("tau", "0.6"))
    a, b = q.get("a", ""), q.get("b", "")
    if b not in state.profiles:
        raise KeyError(f"unknown case: {b}")
    if a == "new":
        with state.lock:
            item = state.pending.get(q.get("id", ""))
        if item is None:
            raise KeyError("This analysis is unknown or already saved; run it again.")
        pa = item[1]["profile"]
    elif a in state.profiles:
        pa = state.profiles[a]
    else:
        raise KeyError(f"unknown case: {a}")
    return {"a": a, "b": b, **explain.pair(pa, state.profiles[b], tau)}


def analyze_payload(state: State, body: dict) -> Dict[str, Any]:
    tau = parse_tau(body.get("tau", 0.6))
    case, notes = an.build_case(url=str(body.get("url") or ""), text=str(body.get("text") or ""))
    if case is None:
        raise ValueError("No article text: " + ("; ".join(notes) or "give a URL or paste the text") + ".")
    res = an.analyse(case, state.profiles, tau, state.llm())
    aid = uuid.uuid4().hex
    with state.lock:
        state.pending[aid] = (case, res)
        while len(state.pending) > MAX_PENDING:
            del state.pending[next(iter(state.pending))]
    numbers = campaign_numbers(state, tau)
    return {"id": aid, "notes": notes, "llm_used": res["llm_used"],
            "decision": {k: res["decision"][k] for k in ("status", "title", "explanation")},
            "reasons": res["reasons"], "thresholds": res["reasons"]["thresholds"],
            "campaigns": [{**row, "no": numbers.get(frozenset(row["members"]))} for row in res["campaigns"]],
            "profile": summary("new", res["profile"]), "joins": res["joins"],
            "neighbours": [{"case": c, "score": round(r["score"], 3), "evidence": r["strong_links"],
                            "campaign": next((n for m, n in numbers.items() if c in m), None),
                            "product": an.case_summary(c, state.profiles[c])["product"],
                            "explanation": explain.pair(res["profile"], state.profiles[c], tau)}
                           for c, r in res["neighbours"]]}


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
                if parts.path == "/api/explain":
                    return self.send_json(200, explain_payload(state, parse_qs(parts.query)))
                if parts.path == "/api/graph":
                    return self.send_json(200, graph_payload(state, parse_tau(parse_qs(parts.query).get("tau", ["0.6"])[0])))
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
