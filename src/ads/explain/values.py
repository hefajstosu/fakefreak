"""The values behind one feature of a pair: what both cases share, what only one has, the texts compared."""
from typing import Any, Dict, Iterable, Optional, Sequence

from ..sim_functions import attributes as A
from ..sim_functions.normalize import norm, stem
from ..sim_functions.primitives import name_similarity

MATCH = 0.5        # a pair of names counts as shared from this similarity on
MAX_ITEMS = 12     # values listed per side and feature
TEXT_CHARS = 280   # free text quoted per side


def person(p: Dict[str, Any]) -> str:
    return p.get("name") or f"unnamed {p.get('category_or_role') or 'person'}"


def _product(p: Optional[Dict[str, Any]]) -> Optional[str]:
    p = p or {}
    name, cat = p.get("exact_name"), p.get("generic_category")
    return f"{name} ({cat})" if name and cat else name or cat


def _greedy(xs: Sequence, ys: Sequence, sim, label=str) -> Dict[str, list]:
    """One-to-one matching, best pairs first (as primitives.best_assignment): shared pairs and the leftovers."""
    pairs = sorted(((sim(x, y), i, j) for i, x in enumerate(xs) for j, y in enumerate(ys)), key=lambda t: -t[0])
    used_x, used_y, matches = set(), set(), []
    for s, i, j in pairs:
        if s < MATCH:
            break
        if i not in used_x and j not in used_y:
            used_x.add(i)
            used_y.add(j)
            matches.append({"a": label(xs[i]), "b": label(ys[j]), "similarity": round(s, 2)})
    return {"shared": matches[:MAX_ITEMS],
            "only_a": [label(x) for i, x in enumerate(xs) if i not in used_x][:MAX_ITEMS],
            "only_b": [label(y) for j, y in enumerate(ys) if j not in used_y][:MAX_ITEMS]}


def _sets(xs: Iterable, ys: Iterable) -> Dict[str, list]:
    sa, sb = {x for x in xs or [] if x}, {y for y in ys or [] if y}
    return {"shared": [{"a": v, "b": v, "similarity": 1.0} for v in sorted(sa & sb)][:MAX_ITEMS],
            "only_a": sorted(sa - sb)[:MAX_ITEMS], "only_b": sorted(sb - sa)[:MAX_ITEMS]}


def _clip(t: Optional[str]) -> Optional[str]:
    return None if not t else t if len(t) <= TEXT_CHARS else t[:TEXT_CHARS].rsplit(" ", 1)[0] + " …"


def _text(a: Optional[str], b: Optional[str]) -> Dict[str, Any]:
    """Both texts and the words behind the stem overlap that text_similarity scores."""
    def words(t):
        return [w for w in norm(t).split() if len(w) >= 4]
    stems_b = {stem(w) for w in words(b)}
    shared, seen = [], set()
    for w in words(a):
        if stem(w) in stems_b and stem(w) not in seen:
            seen.add(stem(w))
            shared.append(w)
    return {"a": _clip(a), "b": _clip(b), "shared_words": shared[:MAX_ITEMS * 2]}


def _url_tokens(t: Optional[dict]) -> list:
    t = t or {}
    return A.url_tokens((t.get("redirect_chain") or []) + (t.get("urls_and_domains") or []))


def values(kind: str, va: Any, vb: Any, ignore: frozenset) -> Dict[str, Any]:
    """Shown values of one feature for the pair; `kind` comes from catalog.FEATURES."""
    if kind == "enum":
        return {"a": va, "b": vb}
    if kind == "product":
        return {"a": _product(va), "b": _product(vb)}
    if kind == "text":
        return _text(va, vb)
    if kind == "set":
        return _sets(va, vb)
    if kind == "anchor":
        return _sets([x for x in va or [] if x not in ignore], [y for y in vb or [] if y not in ignore])
    if kind == "domains":
        return _sets(A.domains(va), A.domains(vb))
    if kind == "people":
        return _greedy(va or [], vb or [], A.person_pair, person)
    if kind == "names":
        return _greedy(va or [], vb or [], name_similarity)
    if kind == "infra":
        return _sets(A.infra_tokens(va), A.infra_tokens(vb))
    if kind == "url":
        return _sets(_url_tokens(va), _url_tokens(vb))
    if kind == "structure":  # page skeletons: how many pages were compared on each side
        return {"pages_a": len((va or {}).get("structure") or []), "pages_b": len((vb or {}).get("structure") or [])}
    if kind == "images":     # page image kits: counts only, hashes mean nothing to a reader
        ia, ib = set((va or {}).get("images") or []), set((vb or {}).get("images") or [])
        return {"shared_count": len(ia & ib), "images_a": len(ia), "images_b": len(ib)}
    if kind == "amounts":
        va, vb = va or {}, vb or {}
        out = _greedy(va.get("amounts") or [], vb.get("amounts") or [], A.amount_pair)
        for key in ("dates", "locations"):
            part = _greedy(va.get(key) or [], vb.get(key) or [], name_similarity)
            for k in out:
                out[k] += part[k]
        return out
    return {}


def empty(v: Any) -> bool:
    if isinstance(v, dict) and set(v) == {"structure", "images"}:  # page fingerprints
        return not v["structure"] and not v["images"]
    if isinstance(v, dict):
        return all(empty(x) for x in v.values())
    return v is None or v == [] or (isinstance(v, str) and not v.strip())
