"""Why two cases are linked, why a campaign holds together, why a new article joined a campaign or did not.

Reporting only: nothing here changes a score, a group or a decision. Every number is recomputed with the same
functions and settings as `similarity.score()`, so a pair explanation always adds up to the score.

    pair(a, b, tau)                  per-feature and per-group shares of the score, shared and differing values,
                                     features skipped for missing data, the evidence, the score without each group
    campaign(members, ..., tau)      rule that formed it, shared signature, cohesion, nearest other campaign
    assignment(assign_result, tau)   per campaign: did a new article join it, on which rule
    family_assignment(...)           the same per family of campaigns
    decision_reasons(dec, ...)       which rule of decision.decide() fired, with the numbers it compared

    python -m ads.explain 1 2 [--tau 0.6]   |   python -m ads.explain --campaigns
"""
from .campaign import campaign
from .catalog import evidence_items
from .joins import assignment, decision_reasons, family_assignment
from .pair import pair

__all__ = ["campaign", "evidence_items", "assignment", "decision_reasons", "family_assignment", "pair"]
