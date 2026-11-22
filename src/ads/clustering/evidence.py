"""Hard evidence as must-link edges: some shared traces join two articles whatever their score.

Evidence labels come from `sim_functions.evidence.strong_links`. Shared domains and files are NOT must-links by
default (a shared mass domain would chain unrelated campaigns); they still show up as supporting evidence.
"""
from typing import Any, Dict, Iterable

DEFAULT_MUST_LINK = ("shared tracker ID", "shared session/form endpoint", "same sponsoring page")
# A pair this similar is the same ad again (a variant or a re-post with swapped surface details): it joins like hard
# evidence. Same value as decision.CONFIRM_SCORE, so a "confirmed" verdict always means the article joined that
# campaign. No pair of different sample campaigns comes near it (the highest sample pair scores 0.65).
SAME_CONTENT_SCORE = 0.80


def is_must_link(result: Dict[str, Any], kinds: Iterable[str] = DEFAULT_MUST_LINK) -> bool:
    kinds = tuple(kinds)
    return any(s.startswith(kinds) for s in result.get("strong_links", []))


def joins_alone(result: Dict[str, Any], same_content: float = SAME_CONTENT_SCORE) -> bool:
    """True when this pair is grouped whatever the rest of the campaign looks like: hard evidence (must-link) or a
    near-identical content score. Average link still decides everything else."""
    return is_must_link(result) or result.get("score", 0.0) >= same_content
