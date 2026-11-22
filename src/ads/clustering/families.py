"""Second level: families of campaigns (same kind of scam and story, or a shared tool; no proof of one operator)."""
from typing import Any, Dict, List, Optional

from .evidence import FAMILY_SCORE, is_family_link
from .linkage import components
from .pairs import Profiles, Scores, pair, pair_scores


def scam_type(p: Dict[str, Any]) -> Optional[str]:
    return (p.get("core_narrative") or {}).get("ad_goal_scam_type")


def related(pa: Dict[str, Any], pb: Dict[str, Any], result: Dict[str, Any], family_tau: float = FAMILY_SCORE) -> bool:
    """The family rule for one pair: the same scam type and a score >= family_tau or family-level evidence."""
    return scam_type(pa) == scam_type(pb) and (result["score"] >= family_tau or is_family_link(result))


def hierarchy(profiles: Profiles, campaigns: List[List[str]], family_tau: float = FAMILY_SCORE,
              scores: Optional[Scores] = None) -> List[List[int]]:
    """Campaign indexes grouped into families, largest first: two campaigns are one family when some pair of their
    members is `related`."""
    scores = scores if scores is not None else pair_scores(profiles)
    edges = [(i, j) for i in range(len(campaigns)) for j in range(i + 1, len(campaigns))
             if any(related(profiles[a], profiles[b], pair(scores, a, b), family_tau)
                    for a in campaigns[i] for b in campaigns[j])]
    fams = components(range(len(campaigns)), edges)
    return sorted((sorted(f) for f in fams), key=lambda f: (-len(f), f))
