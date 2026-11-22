"""Place a new article into the existing campaigns."""
from typing import Any, Dict, List, Optional

from ..similarity import score
from .evidence import joins_alone
from .linkage import cluster
from .pairs import Profiles


def assign(new: Dict[str, Any], profiles: Profiles, tau: float, groups: Optional[List[List[str]]] = None,
           top: int = 5) -> Dict[str, Any]:
    """Rank the database by similarity to `new` and say which campaigns it joins. A campaign is joined on hard
    evidence or near-identical content with a member (evidence.joins_alone), or when the MEAN score to its members
    reaches tau (the clustering rule). Returns {"neighbours": top (id, result), "joins": [campaign],
    "group_scores": {campaign: {"mean", "joins_alone"}}, "scores": {id: result}}."""
    results = {cid: score(new, p) for cid, p in profiles.items()}
    groups = groups if groups is not None else cluster(profiles, tau)
    joined, detail = [], {}
    for g in groups:
        mean = sum(results[c]["score"] for c in g) / len(g)
        linked = any(joins_alone(results[c]) for c in g)
        detail[tuple(g)] = {"mean": round(mean, 4), "joins_alone": linked}
        if linked or mean >= tau:
            joined.append(g)
    ranked = sorted(results.items(), key=lambda x: -x[1]["score"])
    return {"neighbours": ranked[:top], "joins": joined, "group_scores": detail, "scores": results}
