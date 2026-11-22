"""Grouping of articles into campaigns and families. All grouping logic lives here.

    from ads.clustering import pair_scores, cluster, hierarchy, assign
    scores = pair_scores(profiles)                  # N x N table of ads.similarity.score results
    campaigns = cluster(profiles, tau, scores)      # average-link groups, must-link on hard evidence
    families = hierarchy(profiles, campaigns, family_tau, scores)   # indexes into `campaigns`
    assign(new_profile, profiles, tau)              # where a new article goes

Pass `variants={case_id: [variant profiles]}` to pair_scores/cluster/assign to use synthetic variants as extra
comparisons. They only raise a real article's score; they are never members of any group, and are never compared with each
other. `variant_gate=0.15` skips the variant comparisons of pairs that score below it and share no hard evidence.

`ads/cluster.py` only re-exports these names for older callers.
"""
from .assign import assign
from .evidence import DEFAULT_MUST_LINK, SAME_CONTENT_SCORE, is_must_link, joins_alone
from .families import hierarchy
from .linkage import average_score, cluster
from .pairs import best_score, pair, pair_scores
from .variants import load_all_variants, load_variants

__all__ = ["pair_scores", "best_score", "load_variants", "load_all_variants", "pair", "cluster", "average_score", "hierarchy", "assign", "is_must_link", "joins_alone", "SAME_CONTENT_SCORE",
           "DEFAULT_MUST_LINK"]
