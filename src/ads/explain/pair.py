"""Why two cases score what they do."""
from typing import Any, Dict, Optional

from ..sim_functions import compare_all, load_config
from ..sim_functions import get
from ..sim_functions.evidence import strong_links
from .catalog import FEATURES, GROUPS, evidence_items
from .values import empty, values


def pair(a: Dict[str, Any], b: Dict[str, Any], tau: Optional[float] = None) -> Dict[str, Any]:
    """Full explanation of score(a, b). Feature and group contributions are shares of `score` and add up to it;
    `loss` is how much a feature pulled the score below 1; `without` is the score with a group switched off
    (renormalised, like missing data) and, with `tau`, `crosses_tau` says whether that moves the pair across it.
    `missing` says on which side a skipped feature had no data; `informative` marks weight-0 features."""
    cfg = load_config()
    res = compare_all(a, b, weights=cfg["weights"], ignore=cfg["ignore"], supporting=cfg["supporting"])
    s, total = round(res["score"] or 0.0, 4), res["used_weight"]
    feats, num, by_group = [], 0.0, {}
    for name, f in res["features"].items():
        group, kind, path = FEATURES.get(name, ("other", "", ""))
        va, vb = (get(a, path), get(b, path)) if path else (None, None)
        row = {"feature": name, "group": group, "similarity": f["similarity"], "weight": f["weight"],
               "contribution": f["contribution"], "loss": None, "missing": None,
               "values": values(kind, va, vb, cfg["ignore"])}
        if f["contribution"] is not None:
            ws = f["weight"] * f["similarity"]
            num += ws
            row["loss"] = round(f["weight"] * (1 - f["similarity"]) / total, 4) if total else None
            g = by_group.setdefault(group, {"weight": 0.0, "ws": 0.0, "contribution": 0.0, "features": []})
            g["weight"] += f["weight"]
            g["ws"] += ws
            g["contribution"] += f["contribution"]
            g["features"].append(name)
        elif f["similarity"] is None:
            ea, eb = empty(va), empty(vb)
            row["missing"] = "both" if ea and eb else "a" if ea else "b" if eb else "unknown"
        elif name in cfg["supporting"]["features"]:
            row["missing"] = "supporting"  # a supporting feature that disagrees: dropped, not counted against
        elif not f["weight"]:
            row["informative"] = True
        feats.append(row)
    groups = []
    for key in list(GROUPS) + ["other"]:
        g = by_group.get(key)
        if not g:
            continue
        rest = total - g["weight"]
        item = {"group": key, "contribution": round(g["contribution"], 4), "weight": round(g["weight"], 3),
                "similarity": round(g["ws"] / g["weight"], 4) if g["weight"] else None,
                "without": round((num - g["ws"]) / rest, 4) if rest > 0 else None, "features": g["features"]}
        if tau is not None and item["without"] is not None:
            item["crosses_tau"] = (s >= tau) != (item["without"] >= tau)
        groups.append(item)
    feats.sort(key=lambda r: (r["contribution"] is None, -(r["contribution"] or 0), r["feature"]))
    ev = evidence_items(strong_links(a, b))
    return {"score": s, "must_link": any(e["must_link"] for e in ev), "evidence": ev, "groups": groups,
            "features": feats, "tau": tau}
