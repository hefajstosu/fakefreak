"""Measurements against the gold labels (data/gold), each a command:

    python -m ads.evaluation.evaluate    ranking constraints, pairwise P/R/F1 of campaigns and families, score matrix
    python -m ads.evaluation.quality     the organiser's test replayed: new material against known campaigns
    python -m ads.evaluation.features    usefulness of every feature (coverage, AUC, false hits)
    python -m ads.evaluation.robustness  feature groups switched off; material removed from a case
    python -m ads.evaluation.ablation    the database with and without synthetic variants
    python -m ads.evaluation.bench       how comparison time grows with the database
"""
