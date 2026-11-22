"""Second level: families of campaigns (same kind of scam and story, or a shared tool; no proof of one operator)."""
from typing import Any, Dict, List, Optional

from .evidence import is_family_link
from .linkage import components
from .pairs import Profiles, Scores, pair, pair_scores


def _scam(p: Dict[str, Any]) -> Optional[str]:
    return (p.get("core_narrative") or {}).get("ad_goal_scam_type")


def hierarchy(profiles: Profiles, campaigns: List[List[str]], family_tau: float,
              scores: Optional[Scores] = None) -> List[List[int]]:
    """Campaign indexes grouped into families, largest first: two campaigns are one family when some pair of their
    members has the same scam type and a score >= family_tau or family-level evidence (evidence.is_family_link)."""
    scores = scores if scores is not None else pair_scores(profiles)

    def related(a: str, b: str) -> bool:
        r = pair(scores, a, b)
        return _scam(profiles[a]) == _scam(profiles[b]) and (r["score"] >= family_tau or is_family_link(r))

    edges = [(i, j) for i in range(len(campaigns)) for j in range(i + 1, len(campaigns))
             if any(related(a, b) for a in campaigns[i] for b in campaigns[j])]
    fams = components(range(len(campaigns)), edges)
    return sorted((sorted(f) for f in fams), key=lambda f: (-len(f), f))
