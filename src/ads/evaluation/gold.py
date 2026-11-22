"""The gold labels (data/gold) and the measures every evaluation shares.

Levels: strict = same campaign or same template; broad = strict or same scheme (a family of campaigns).
"""
import json
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ..paths import gold_file

STRICT = {"same_campaign", "same_template"}
BROAD = STRICT | {"same_scheme"}
Pair = Tuple[str, str]


def load_gold(path: Optional[str] = None) -> dict:
    return json.load(open(path or gold_file(), encoding="utf-8"))


def labelled(profiles: Dict[str, dict], gold: dict) -> Dict[str, dict]:
    """The profiles that the gold labels cover (cases saved from the panel are not labelled)."""
    ids = set(gold.get("case_ids") or profiles)
    return {k: v for k, v in profiles.items() if k in ids}


def gold_pairs(gold: dict, levels: Set[str]) -> Set[Pair]:
    pairs: Set[Pair] = set()
    for g in gold["groups"]:
        if g["level"] in levels:
            pairs |= {tuple(sorted(p)) for p in combinations(g["members"], 2)}
    return pairs


def partners(cid: str, pairs: Iterable[Pair]) -> Set[str]:
    return {b if a == cid else a for a, b in pairs if cid in (a, b)}


def group_pairs(groups: Iterable[Iterable[str]]) -> Set[Pair]:
    return {tuple(sorted(p)) for g in groups for p in combinations(g, 2)}


def prf(pred: Set[Pair], truth: Set[Pair]) -> Tuple[float, float, float]:
    tp = len(pred & truth)
    p = tp / len(pred) if pred else 1.0
    r = tp / len(truth) if truth else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def auc(pos: List[float], neg: List[float]) -> float:
    """Probability that a positive pair scores above a negative one (ties count half); NaN without both."""
    if not pos or not neg:
        return float("nan")
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))
