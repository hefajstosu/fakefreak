"""Second level: families of campaigns (same kind of scam and story, no proof of one operator)."""
from typing import Any, Dict, List, Optional

from .evidence import is_family_link
from .linkage import _components
from .pairs import Profiles, Scores, Variants, pair, pair_scores


def _scam(p: Dict[str, Any]) -> Optional[str]:
    return (p.get("core_narrative") or {}).get("ad_goal_scam_type")


def hierarchy(profiles: Profiles, campaigns: List[List[str]], family_tau: float,
              scores: Optional[Scores] = None, variants: Optional[Variants] = None,
              variant_gate: Optional[float] = None) -> List[List[int]]:
    """Group campaign indexes into families.

    Two campaigns are in one family when some pair of their members has the same scam type and either a score
    >= family_tau or family-level evidence (shared platform endpoints, evidence.is_family_link). Returns lists of
    indexes into `campaigns`, largest first. Singletons are kept.
    """
    scores = scores if scores is not None else pair_scores(profiles, variants, variant_gate)
    edges = []
    for i in range(len(campaigns)):
        for j in range(i + 1, len(campaigns)):
            if any(_scam(profiles[a]) == _scam(profiles[b]) and (pair(scores, a, b)["score"] >= family_tau or
                                                                  is_family_link(pair(scores, a, b)))
                   for a in campaigns[i] for b in campaigns[j]):
                edges.append((i, j))
    fams = _components(list(range(len(campaigns))), edges)
    return sorted((sorted(f) for f in fams), key=lambda f: (-len(f), f))
