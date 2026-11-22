"""Grouping of articles into campaigns and families of campaigns.

    scores = pair_scores(profiles)                       # N x N table of similarity.score results
    campaigns = cluster(profiles, tau, scores)           # must-links first, then average link at tau
    families = hierarchy(profiles, campaigns, family_tau, scores)   # indexes into `campaigns`
    assign(new_profile, profiles, tau, campaigns)        # which campaigns a new article joins

Synthetic variants ({case id: [variant profiles]}, load_variants) can be given to pair_scores as extra comparisons:
they only raise the score of their parent's pairs and are never grouped.
"""
from .assign import assign
from .evidence import FAMILY_SCORE, SAME_CONTENT_SCORE, TAU, is_family_link, is_must_link, joins_alone
from .families import hierarchy, related, scam_type
from .linkage import average_score, cluster, components
from .pairs import best_score, pair, pair_scores
from .variants import load_variants

__all__ = ["assign", "FAMILY_SCORE", "SAME_CONTENT_SCORE", "TAU", "is_family_link", "is_must_link",
           "joins_alone", "hierarchy", "related", "scam_type", "average_score", "cluster", "components", "best_score", "pair", "pair_scores",
           "load_variants"]
