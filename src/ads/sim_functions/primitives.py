"""Generic similarity measures. Each returns a float in [0, 1], or None when there is no evidence either way
(empty or unknown on a side): None means "drop this feature", never "dissimilar"."""
import difflib
from functools import lru_cache
from typing import Callable, Iterable, Optional, Sequence

from .normalize import norm, stem, stems

Score = Optional[float]


def exact(a, b) -> Score:
    """Closed enums (scam type, topic, templates). None if either side is unknown."""
    if a is None or b is None:
        return None
    return 1.0 if a == b else 0.0


def jaccard(a: Iterable, b: Iterable, both_empty: Score = None) -> Score:
    """|A ∩ B| / |A ∪ B|; both_empty is returned when neither side has a value."""
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return both_empty
    return len(sa & sb) / len(sa | sb)


def closed_set(a: Iterable, b: Iterable) -> Score:
    """Jaccard of closed-vocabulary lists (persuasion devices, funnel stages): nothing on both sides is agreement."""
    return jaccard(a, b, both_empty=1.0)


def name_similarity(a, b) -> float:
    """Similarity of two names (person, company, outlet, prop, keyword), tolerant of Polish inflection: 1.0 when equal
    after normalisation, 0.9 when a one-word name is contained in the other ('Glapińskiego' vs 'Adam Glapiński'),
    otherwise the best of stem Jaccard and a typo-tolerant string ratio."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return 1.0 if na == nb else _string_similarity(na, nb)


@lru_cache(maxsize=262144)  # pure in (na, nb); names recur across every pair of the database
def _string_similarity(na: str, nb: str) -> float:
    ta, tb = stems(na), stems(nb)
    inter = len(ta & tb)
    best = inter / len(ta | tb) if ta | tb else 0.0
    if inter and inter == min(len(ta), len(tb)) == 1:
        best = max(best, 0.9)
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    return max(best, ratio) if ratio >= 0.85 else best


def best_assignment(a: Sequence, b: Sequence, sim: Callable) -> float:
    """Greedy one-to-one matching of two short lists, best pairs first; the sum of matched similarities."""
    pairs = sorted(((sim(x, y), i, j) for i, x in enumerate(a) for j, y in enumerate(b)), reverse=True)
    used_a, used_b, total = set(), set(), 0.0
    for s, i, j in pairs:
        if s <= 0:
            break
        if i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
            total += s
    return total


def set_similarity(a: Sequence, b: Sequence, pair_sim: Callable = name_similarity) -> Score:
    """Soft Jaccard for lists of names: matched similarity / size of the longer list. Nothing on both sides is None
    (no evidence); one side empty is 0 (a real mismatch)."""
    a, b = [x for x in a or [] if x], [x for x in b or [] if x]
    if not a and not b:
        return None
    if not a or not b:
        return 0.0
    return best_assignment(a, b, pair_sim) / max(len(a), len(b))


def numeric_similarity(x: float, y: float) -> float:
    """Relative closeness 1 - |x - y| / max(|x|, |y|): 137 vs 140 -> 0.98, 50 vs 5 -> 0.1."""
    return 1.0 if x == y else max(0.0, 1.0 - abs(x - y) / max(abs(x), abs(y)))


def text_similarity(a, b) -> Score:
    """Free text (narrative, promise, call to action, summary): Jaccard of word stems."""
    if not a or not b or not str(a).strip() or not str(b).strip():
        return None
    return jaccard({stem(t) for t in norm(a).split()}, {stem(t) for t in norm(b).split()})
