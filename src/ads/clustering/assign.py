"""Place a new article into the existing groups."""
from typing import Any, Dict, Optional

from .evidence import joins_alone
from .linkage import cluster
from .pairs import Profiles, Variants, best_score


def assign(new: Dict[str, Any], profiles: Profiles, tau: float, top: int = 5,
           groups: Optional[list] = None, variants: Optional[Variants] = None, variant_gate: Optional[float] = None) -> Dict[str, Any]:
    """Rank existing articles by similarity to `new` and say which groups it joins, else that it is new.

    A group is joined when `new` has hard evidence with one of its members or is near-identical to one
    (evidence.joins_alone), or when the MEAN score to its members reaches tau (same rule as the average-link clustering). Several groups may be joined.
    `variants` ({case_id: [profiles]}) are the synthetic variants of the database articles: they can raise the
    score of their parent but are never groups or members. The new article's own variants are not used.
    Returns {"neighbours": [(id, score result)], "joins": [group], "is_new_group": bool, "group_scores": {...},
    "scores": {id: score result}} (scores of `new` against every article, used to explain the joins).
    """
    variants = variants or {}
    results = {cid: best_score(new, p, None, variants.get(cid), variant_gate) for cid, p in profiles.items()}
    ranked = sorted(results.items(), key=lambda x: -x[1]["score"])
    groups = groups if groups is not None else cluster(profiles, tau, variants=variants, variant_gate=variant_gate)
    joined, detail = [], {}
    for g in groups:
        mean = sum(results[c]["score"] for c in g) / len(g)
        linked = any(joins_alone(results[c]) for c in g)
        detail[tuple(g)] = {"mean": round(mean, 4), "hard_evidence": linked}
        if linked or mean >= tau:
            joined.append(g)
    return {"neighbours": ranked[:top], "joins": joined, "is_new_group": not joined, "group_scores": detail,
            "scores": results}
