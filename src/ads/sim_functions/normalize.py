"""Text normalisation helpers shared by the similarity functions (stdlib only)."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_PUNCT = re.compile(r"[^\w\s%]", re.UNICODE)
_SPACES = re.compile(r"\s+")


@lru_cache(maxsize=65536)  # pure; the same strings recur in every pair comparison
def fold(s: str) -> str:
    """Lowercase and strip diacritics (Polish 'ł' is not decomposed by NFKD, so map it by hand)."""
    s = s.lower().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s) -> str:
    """Canonical form used for all string comparisons: folded, no punctuation, single spaces."""
    if s is None:
        return ""
    return _norm(str(s))


@lru_cache(maxsize=65536)
def _norm(s: str) -> str:
    return _SPACES.sub(" ", _PUNCT.sub(" ", fold(s))).strip()


def stem(token: str, n: int = 5) -> str:
    """Crude Polish 'stemmer': keep the first n characters.

    Good enough to match inflected forms of a name (Glapiński / Glapińskiego -> 'glapi').
    Swap for a real lemmatiser (spaCy 'pl', Morfeusz) if the gold set shows misses.
    """
    return token[:n]


def stems(s) -> set:
    return set(_stems(norm(s)))


@lru_cache(maxsize=65536)
def _stems(normed: str) -> frozenset:
    return frozenset(stem(t) for t in normed.split())


_NUMBER = re.compile(r"\d[\d\s ]*(?:[.,]\d+)?")
_CURRENCIES = {"pln": "pln", "zl": "pln", "eur": "eur", "usd": "usd", "gbp": "gbp", "chf": "chf",
               "€": "eur", "$": "usd"}
_MULTIPLIERS = (("tys", 1e3), ("mln", 1e6), ("milion", 1e6), ("mld", 1e9), ("miliard", 1e9))


def parse_amount(s):
    """Parse strings like '274 PLN', '-50%', '150 tysięcy', '17 pakietów' -> (value, kind) or None.

    kind is 'pct', a currency code, or 'count'. Values of different kinds are never compared.
    """
    if s is None:
        return None
    return _parse_amount(str(s))


@lru_cache(maxsize=65536)
def _parse_amount(raw: str):
    m = _NUMBER.search(raw)
    if not m:
        return None
    try:
        value = float(re.sub(r"[\s ]", "", m.group()).replace(",", "."))
    except ValueError:
        return None
    rest = fold(raw[m.end():]) + " " + fold(raw[:m.start()])
    for prefix, mult in _MULTIPLIERS:
        if re.search(r"\b" + prefix, rest):
            value *= mult
            break
    if "%" in raw:
        return value, "pct"
    for token in re.findall(r"[\w€$]+", rest):
        if token in _CURRENCIES:
            return value, _CURRENCIES[token]
    return value, "count"
