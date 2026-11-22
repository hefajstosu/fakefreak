"""Hard evidence as must-link edges: some shared traces join two articles whatever their score.

Evidence labels come from `sim_functions.evidence.strong_links`. Shared domains and files are NOT must-links by
default (a shared mass domain would chain unrelated campaigns); they still show up as supporting evidence.
"""
from typing import Any, Dict, Iterable

DEFAULT_MUST_LINK = ("shared tracker ID", "shared session/form endpoint", "same sponsoring page")


def is_must_link(result: Dict[str, Any], kinds: Iterable[str] = DEFAULT_MUST_LINK) -> bool:
    kinds = tuple(kinds)
    return any(s.startswith(kinds) for s in result.get("strong_links", []))
