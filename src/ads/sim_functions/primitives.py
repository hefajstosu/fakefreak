"""Generic similarity building blocks. Every function returns a float in [0, 1],
or None when there is no evidence either way (empty / unknown on one or both sides).
None means "drop this feature", never "dissimilar" (see aggregate.py)."""
from __future__ import annotations

import difflib
import math
from typing import Callable, Iterable, Optional, Sequence

from .normalize import norm, stem, stems

Score = Optional[float]


def exact(a, b) -> Score:
    """Closed enums (scam type, topic, templates, language). None if either side is unknown."""
    if a is None or b is None:
        return None
    return 1.0 if a == b else 0.0


def jaccard(a: Iterable, b: Iterable, both_empty: Score = None) -> Score:
    """Plain set overlap |A∩B| / |A∪B|. Use both_empty=1.0 where 'nothing on both sides' is a
    real agreement (e.g. persuasion_devices), and the default None where it is just missing data."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return both_empty
    return len(sa & sb) / len(sa | sb)


def name_similarity(a, b, soft: Optional[Callable[[str, str], float]] = None) -> float:
    """Similarity of two names (person, company, outlet, prop, keyword), tolerant of Polish inflection.

    1.0 identical after normalisation; 0.9 a single-token mention contained in the other name
    ('Glapińskiego' vs 'Adam Glapiński'); otherwise the best of stem-Jaccard and a typo-tolerant
    string ratio. `soft` is an optional hook (e.g. embedding cosine rescaled to [0, 1]) that lets a
    same-sector swap ('PGE' vs 'Tauron') earn partial credit.
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = stems(na), stems(nb)
    inter = len(ta & tb)
    best = inter / len(ta | tb) if ta | tb else 0.0
    if inter and inter == min(len(ta), len(tb)) and min(len(ta), len(tb)) == 1:
        best = max(best, 0.9)
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    if ratio >= 0.85:
        best = max(best, ratio)
    if soft is not None:
        best = max(best, soft(na, nb))
    return best


def best_assignment(a: Sequence, b: Sequence, sim: Callable) -> float:
    """Greedy one-to-one matching of two small lists; returns the SUM of matched pair similarities.
    (Optimal assignment would need scipy; lists here have a handful of items, greedy is enough.)"""
    pairs = sorted(((sim(x, y), i, j) for i, x in enumerate(a) for j, y in enumerate(b)), reverse=True)
    used_a, used_b, total = set(), set(), 0.0
    for s, i, j in pairs:
        if s <= 0:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        total += s
    return total


def set_similarity(a: Sequence, b: Sequence, pair_sim: Callable = name_similarity,
                   both_empty: Score = None) -> Score:
    """Soft Jaccard-like score for lists of names: matched similarity / size of the larger list.
    One side empty and the other not -> 0.0 (a real mismatch); both empty -> both_empty."""
    a, b = [x for x in (a or []) if x], [x for x in (b or []) if x]
    if not a and not b:
        return both_empty
    if not a or not b:
        return 0.0
    return best_assignment(a, b, pair_sim) / max(len(a), len(b))


def numeric_similarity(x: float, y: float) -> float:
    """Relative closeness: 1 - |x-y| / max(|x|,|y|). 137 vs 140 -> 0.98, 50 vs 5 -> 0.1."""
    if x == y:
        return 1.0
    return max(0.0, 1.0 - abs(x - y) / max(abs(x), abs(y)))


def cosine(u: Sequence[float], v: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    nu, nv = math.sqrt(sum(x * x for x in u)), math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0


def text_similarity(a, b, embed: Optional[Callable] = None, floor: float = 0.7) -> Score:
    """Free-text similarity (narrative, promise, CTA, canonical text).

    With `embed` (callable: list[str] -> list[vector], see embeddings.py) uses cosine. e5 models give
    unrelated texts a cosine of ~0.7, so the score is rescaled: (cos - floor) / (1 - floor), clipped
    to [0, 1]; tune `floor` on the gold set. Without `embed` it falls back to stem-Jaccard of the
    words, which is crude but needs no model (handy for tests).
    """
    if not a or not b or not str(a).strip() or not str(b).strip():
        return None
    if embed is None:
        return jaccard({stem(t) for t in norm(a).split()}, {stem(t) for t in norm(b).split()})
    va, vb = embed([str(a), str(b)])
    return min(1.0, max(0.0, (cosine(va, vb) - floor) / (1.0 - floor)))
