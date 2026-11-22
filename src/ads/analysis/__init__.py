"""One new article against the database, with no UI code (the web panel and the evaluation use it).

    case, notes = build_case(url, text, images, html_files, hars, videos, text_files)   # material -> case_input
    result = analyse(case, profiles, tau, client)   # duplicate check, LLM profile (skipped for a repeat), compare
    result = compare(profile, fingerprint, profiles, tau)   # no LLM: duplicates, neighbours, joins, verdict, reasons
    groups = groups_overview(profiles, tau)         # campaigns with family, members, links and explanation
"""
from .case import FILE_KINDS, MAX_CREATIVES, build_case, classify_files
from .compare import analyse, compare
from .index import campaigns, families, pair_table, reset
from .views import case_summary, groups_overview

__all__ = ["FILE_KINDS", "MAX_CREATIVES", "build_case", "classify_files", "analyse", "compare",
           "campaigns", "families", "pair_table", "reset", "case_summary", "groups_overview"]
