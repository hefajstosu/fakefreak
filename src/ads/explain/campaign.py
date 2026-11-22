"""Why the members of a campaign are together, and why it is separate from the nearest other campaign."""
import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from .. import clustering
from ..clustering.pairs import Scores
from ..preprocess.domain_meta import linking_facts
from ..sim_functions import get
from ..sim_functions.evidence import GENERIC_FILES
from ..sim_functions.normalize import norm
from ..urls import domains
from .catalog import FEATURES
from .values import person

# features whose values members can share, infrastructure first
SIGNATURE = ("tracker_ids", "redirect_chain_domains", "dom_and_form_clues", "infra_metadata", "scam_type", "topic",
             "ad_creative_template", "landing_page_template", "persuasion_devices", "product_name", "featured_people",
             "companies", "impersonated_media", "keywords", "logos_and_badges")


def _path(feature: str) -> str:
    return "entities.product_or_platform.exact_name" if feature == "product_name" else FEATURES[feature][2]


def _member_values(feature: str, raw: Any) -> Dict[str, str]:
    """{normalised value: shown value} of one member for one signature feature."""
    if raw is None:
        return {}
    if feature == "redirect_chain_domains":
        raw = domains(raw)
    elif feature == "infra_metadata":  # only facts that can link (no dates, registrars or CDNs on their own)
        raw = linking_facts(raw)
    elif feature == "dom_and_form_clues":  # boilerplate files are never evidence
        raw = [c for c in raw if not (c.startswith("file:") and c[5:].lower() in GENERIC_FILES)]
    out = {}
    for x in raw if isinstance(raw, list) else [raw]:
        if isinstance(x, dict) and not x.get("name"):
            continue  # an unnamed person is not a shared identity
        shown = person(x) if isinstance(x, dict) else str(x)
        if norm(shown):
            out.setdefault(norm(shown), shown)
    return out


def signature(members: Sequence[str], profiles: Dict[str, dict]) -> List[Dict[str, Any]]:
    """Values found in at least two members and in at least half of them, in SIGNATURE order (infrastructure first),
    most widely shared first within a feature."""
    n = len(members)
    if n < 2:
        return []
    need = max(2, math.ceil(n / 2))
    out = []
    for feature in SIGNATURE:
        count, shown, who = Counter(), {}, {}
        for c in members:
            for key, val in _member_values(feature, get(profiles[c], _path(feature))).items():
                count[key] += 1
                shown.setdefault(key, val)
                who.setdefault(key, []).append(c)
        out += [{"feature": feature, "group": FEATURES[feature][0], "value": shown[k], "count": m, "of": n,
                 "cases": who[k]} for k, m in sorted(count.items(), key=lambda kv: (-kv[1], shown[kv[0]])) if m >= need]
    return out


def _rule(members: List[str], parts: List[List[str]], hard: bool, same: bool) -> str:
    if len(members) == 1:
        return "single case"
    if len(parts) > 1:
        return "hard evidence and mean score" if hard or same else "mean score"
    if hard and same:
        return "hard evidence and same content"
    return "hard evidence" if hard else "same content"


def _nearest(members: List[str], scores: Scores, tau: float, campaigns: Sequence[Sequence[str]]) -> Optional[dict]:
    best = None
    for g in campaigns:
        if set(g) == set(members):
            continue
        mean = clustering.average_score(members, list(g), scores)
        if best is None or mean > best["mean"]:
            links = [(x, y, clustering.pair(scores, x, y)) for x in members for y in g]
            x, y, top = max(links, key=lambda t: t[2]["score"])
            best = {"members": list(g), "mean": round(mean, 4), "gap": round(tau - mean, 4),
                    "best_pair": {"a": x, "b": y, "score": top["score"]},
                    "hard_evidence": any(clustering.is_must_link(r) for _, _, r in links),
                    "family_evidence": any(clustering.is_family_link(r) for _, _, r in links)}
    return best


def campaign(members: Sequence[str], profiles: Dict[str, dict], scores: Scores, tau: float,
             campaigns: Sequence[Sequence[str]] = ()) -> Dict[str, Any]:
    """Rule that formed the campaign (hard evidence, same content, mean score), its parts held together by hard
    evidence or same content, their mean score, the shared signature, cohesion, the member that holds on least and
    the nearest other campaign of `campaigns` with why it stayed separate."""
    members = list(members)
    pairs = [(x, y, clustering.pair(scores, x, y)) for i, x in enumerate(members) for y in members[i + 1:]]
    hard = [(x, y) for x, y, r in pairs if clustering.is_must_link(r)]
    same = [(x, y) for x, y, r in pairs if not clustering.is_must_link(r) and clustering.joins_alone(r)]
    parts = sorted((sorted(p) for p in clustering.components(members, hard + same)), key=lambda p: (-len(p), p))
    vals = [r["score"] for _, _, r in pairs]
    out: Dict[str, Any] = {
        "members": members, "rule": _rule(members, parts, bool(hard), bool(same)), "parts": parts,
        "signature": signature(members, profiles),
        "cohesion": {"min": min(vals), "mean": round(sum(vals) / len(vals), 4), "max": max(vals)} if vals else None,
    }
    if len(parts) > 1:  # what average link compared with tau
        out["parts_mean"] = round(sum(clustering.average_score(p, q, scores) for i, p in enumerate(parts)
                                      for q in parts[i + 1:]) / (len(parts) * (len(parts) - 1) / 2), 4)
    if len(members) > 1:
        mean_to_rest = {c: sum(clustering.pair(scores, c, o)["score"] for o in members if o != c) / (len(members) - 1)
                        for c in members}
        weakest = min(mean_to_rest, key=mean_to_rest.get)
        out["weakest"] = {"case": weakest, "mean": round(mean_to_rest[weakest], 4)}
    nearest = _nearest(members, scores, tau, campaigns)
    if nearest:
        out["nearest"] = nearest
    return out
