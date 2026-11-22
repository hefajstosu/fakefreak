"""Which shared traces join two articles whatever their score, and the grouping thresholds.

Evidence labels come from `sim_functions.evidence.strong_links`. Two levels:
- campaign (must-link): a shared tracker ID, the same sponsoring page, the same ad platform campaign ID in the
  funnel URLs or two domains on one (non-CDN, at most 10 names) certificate identify one operator's account;
- family: shared platform endpoint paths identify a shared landing-page tool, two or more identical page images a
  shared page kit, the same non-standard set of tracking parameters a shared tracking template. Several operators can
  use any of them, so they put two cases of the same scam type into one family of campaigns, not into one campaign
  (on the samples they link pages that the gold labels as different campaigns of one scheme).
Shared domains and files are neither (a shared mass domain would chain unrelated campaigns); they stay supporting.
"""
from typing import Any, Dict

from ..sim_functions.evidence import kind_of

MUST_LINK = ("tracker", "page", "adid", "certificate")   # evidence kinds that join a campaign
FAMILY_LINK = ("endpoint", "images", "tracking")         # evidence kinds that join a family of campaigns
TAU = 0.6                 # campaigns: average link merges while the mean score between two groups reaches it
FAMILY_SCORE = 0.30       # families: same scam type and some member pair at least this similar
# A pair this similar is the same ad again (a variant or a re-post with swapped surface details): it joins like hard
# evidence, and the verdict calls it confirmed. The highest sample pair scores 0.67 (one campaign); the highest pair
# of two different sample campaigns 0.43.
SAME_CONTENT_SCORE = 0.80


def _has(result: Dict[str, Any], kinds) -> bool:
    return any(kind_of(s) in kinds for s in result.get("strong_links", []))


def is_must_link(result: Dict[str, Any]) -> bool:
    return _has(result, MUST_LINK)


def is_family_link(result: Dict[str, Any]) -> bool:
    """Evidence that puts two cases of the same scam type into one family (see the module docstring)."""
    return _has(result, FAMILY_LINK)


def joins_alone(result: Dict[str, Any]) -> bool:
    """True when this pair is grouped whatever the rest of the campaign looks like: hard evidence (must-link) or a
    near-identical content score. Average link still decides everything else."""
    return is_must_link(result) or result.get("score", 0.0) >= SAME_CONTENT_SCORE
