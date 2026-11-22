"""The panel's API: shared state and one function per endpoint (the HTTP layer is server.py)."""
import os
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .. import analysis, clustering, database, explain
from ..llm.client import make_client
from . import traits, uploads

MAX_PENDING = 50          # unsaved analyses kept in memory (oldest dropped first, with their files)
GRAPH_EDGES_PER_CASE = 4  # weaker links than these per case are left out of the graph (hard evidence always stays)


class State:
    """Database profiles, campaigns per tau and pending analyses, shared by the request threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.client = None
        self.pending: Dict[str, Tuple[dict, dict]] = {}  # analysis id -> (case, result), until saved
        self.reload()

    def reload(self):
        self.profiles = database.load_profiles()
        self.groups: Dict[float, list] = {}

    def llm(self):
        with self.lock:
            if self.client is None:
                self.client = make_client()
            return self.client

    def overview(self, tau: float) -> list:
        with self.lock:
            if tau not in self.groups:
                self.groups[tau] = analysis.groups_overview(self.profiles, tau)
            return self.groups[tau]

    def remember(self, aid: str, item: Tuple[dict, dict]) -> None:
        with self.lock:
            self.pending[aid] = item
            while len(self.pending) > MAX_PENDING:
                old = next(iter(self.pending))
                del self.pending[old]
                uploads.drop(old)


def parse_tau(value) -> float:
    tau = float(value)
    if not 0.05 <= tau <= 0.95:
        raise ValueError("tau must be between 0.05 and 0.95")
    return round(tau, 2)


def summary(cid: str, profile: dict) -> Dict[str, Any]:
    s = analysis.case_summary(cid, profile)
    s["image_url"] = f"/api/image/{cid}" if s.pop("image") else None
    s["unconfirmed"] = database.case_meta(cid).get("status") == "unconfirmed"
    return s


def status(state: State) -> Dict[str, Any]:
    return {"cases": len(state.profiles), "llm": bool(os.environ.get("GEMINI_API_KEY"))}


def groups(state: State, tau: float) -> Dict[str, Any]:
    return {"tau": tau, "groups": [{"no": i, "family": g["family"], "scam_type": g["scam_type"], "links": g["links"],
                                    "explanation": g["explanation"],
                                    "members": [summary(c, state.profiles[c]) for c in g["members"]]}
                                   for i, g in enumerate(state.overview(tau), 1)]}


def group_by(state: State, trait: str) -> Dict[str, Any]:
    """Cases grouped by the value of one trait (web/traits.py), with the list of traits to choose from."""
    found = traits.group_by(state.profiles, trait) if trait else []  # no trait: only the list to choose from
    return {"trait": trait, "traits": traits.trait_list(),
            "groups": [{"value": g["value"], "members": [summary(c, state.profiles[c]) for c in g["members"]]}
                       for g in found]}


def graph(state: State, tau: float) -> Dict[str, Any]:
    """Cases as nodes (campaign, family), links as edges: every pair with evidence, plus each case's strongest links
    at or above the family threshold (at most GRAPH_EDGES_PER_CASE per case)."""
    where = {c: (i, g["family"]) for i, g in enumerate(state.overview(tau), 1) for c in g["members"]}
    nodes = [{"case": c, "campaign": where[c][0], "family": where[c][1],
              **{k: analysis.case_summary(c, p)[k] for k in ("scam_type", "product")}}
             for c, p in sorted(state.profiles.items())]
    table = analysis.pair_table(state.profiles)
    keep = {k for k, r in table.items() if r["strong_links"]}
    near: Dict[str, list] = {}
    for k, r in table.items():
        if r["score"] >= clustering.FAMILY_SCORE:
            for c in k:
                near.setdefault(c, []).append((r["score"], k))
    for links in near.values():
        keep |= {k for _, k in sorted(links, reverse=True)[:GRAPH_EDGES_PER_CASE]}
    edges = [{"a": a, "b": b, "score": table[(a, b)]["score"], "evidence": table[(a, b)]["strong_links"],
              "must_link": clustering.is_must_link(table[(a, b)]), "family_link": clustering.is_family_link(table[(a, b)]),
              "same_campaign": where[a][0] == where[b][0]} for a, b in sorted(keep)]
    return {"tau": tau, "family_score": clustering.FAMILY_SCORE, "nodes": nodes, "edges": edges}


def explain_pair(state: State, q: Dict[str, str]) -> Dict[str, Any]:
    """explain.pair of two database cases, or (a=new&id=<analysis>) of the analysed article and a database case."""
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
    return {"a": a, "b": b, **explain.pair(pa, state.profiles[b], parse_tau(q.get("tau", "0.6")))}


def analyze(state: State, body: Dict[str, Any], files: Optional[List[uploads.File]] = None) -> Dict[str, Any]:
    """Build the case from the URL, text and files, analyse it and keep it until saved."""
    tau = parse_tau(body.get("tau", 0.6))
    aid = uuid.uuid4().hex
    kinds, notes = uploads.store(aid, files or [])
    try:
        case, more = analysis.build_case(url=str(body.get("url") or ""), text=str(body.get("text") or ""),
                                         images=kinds.get("image", []), html_files=kinds.get("html", []),
                                         hars=kinds.get("har", []), videos=kinds.get("video", []),
                                         text_files=kinds.get("text", []), work_dir=uploads.folder(aid))
        notes += more
        if case is None:
            raise ValueError("Nothing to analyse: " + ("; ".join(notes) or "give a URL, paste the text or add files") + ".")
        res = analysis.analyse(case, state.profiles, tau, state.llm())
    except Exception:
        uploads.drop(aid)
        raise
    state.remember(aid, (case, res))
    numbers = {frozenset(g["members"]): i for i, g in enumerate(state.overview(tau), 1)}
    return {"id": aid, "notes": notes, "llm_used": res["llm_used"],
            "decision": {k: res["decision"][k] for k in ("status", "title", "explanation")},
            "reasons": res["reasons"], "thresholds": res["reasons"]["thresholds"],
            "campaigns": [{**row, "no": numbers.get(frozenset(row["members"]))} for row in res["campaigns"]],
            "families": res["families"], "profile": summary("new", res["profile"]), "joins": res["joins"],
            "neighbours": [{"case": c, "score": round(r["score"], 3), "evidence": r["strong_links"],
                            "campaign": next((n for m, n in numbers.items() if c in m), None),
                            "product": analysis.case_summary(c, state.profiles[c])["product"],
                            "explanation": explain.pair(res["profile"], state.profiles[c], tau)}
                           for c, r in res["neighbours"]]}


def save(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    aid = str(body.get("id"))
    with state.lock:
        item = state.pending.pop(aid, None)
    if item is None:
        raise KeyError("This analysis is unknown or already saved; run it again.")
    case, res = item
    cid = database.save_case(case, res["profile"], res["decision"])  # copies the screenshots into the case
    uploads.drop(aid)
    with state.lock:
        state.reload()
    return {"case_id": cid}
