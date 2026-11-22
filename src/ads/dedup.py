"""Duplicate detection for cases: perceptual image hash, normalised page-text hash and near-duplicate text sketch,
final URL. Used before grouping so the same ad captured twice does not look like a new campaign.

    fp = fingerprint(case_input)                  # dict, JSON-serialisable
    matches = find_duplicates(fp, {cid: fp2, ...})  # [{"case": cid, "reasons": [...]}, ...]

Rules (a case is a duplicate of another when ANY holds):
  * an image has a dHash within IMAGE_MAX_DISTANCE bits (of 64) of an image of the other case;
  * a page text has the same normalised hash, or an estimated shingle Jaccard >= TEXT_NEAR_DUP;
  * the final URL (after redirects) is the same.
Resizing and recompression keep a dHash nearly unchanged; cropping or a different scroll position does not, so
screenshots of the same ad taken differently can still slip through (they then fall to normal similarity).
"""
import hashlib
import json
import os
import re
from typing import Any, Dict, List

import numpy as np
from PIL import Image

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(REPO, "data")
CACHE = os.path.join(REPO, ".cache", "fingerprints.json")
IMAGE_MAX_DISTANCE = 6      # of 64 bits
TEXT_NEAR_DUP = 0.90
SKETCH_K = 256


def dhash(path: str, size: int = 8) -> int:
    im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = np.asarray(im, dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def norm_text(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").casefold())).strip()


def text_hash(t: str) -> str:
    return hashlib.sha1(norm_text(t)[:20000].encode("utf-8")).hexdigest()[:16]


def sketch(t: str, k: int = SKETCH_K) -> List[int]:
    """Bottom-k sketch of 5-word shingle hashes, for near-duplicate detection."""
    words = norm_text(t).split()[:4000]
    hs = {int(hashlib.sha1(" ".join(words[i:i + 5]).encode("utf-8")).hexdigest()[:12], 16)
          for i in range(max(1, len(words) - 4))}
    return sorted(hs)[:k]


def sketch_jaccard(a: List[int], b: List[int]) -> float:
    if not a or not b:
        return 0.0
    union = sorted(set(a) | set(b))[:min(len(a), len(b), SKETCH_K)]
    sa, sb = set(a), set(b)
    return sum(1 for h in union if h in sa and h in sb) / len(union) if union else 0.0


def fingerprint(case: Dict[str, Any], data_dir: str = DATA) -> Dict[str, Any]:
    imgs, texts = [], []
    for p in case["parts"]:
        for im in p.get("images", []):
            path = im if os.path.isabs(im) else os.path.join(data_dir, im)
            if os.path.exists(path):
                try:
                    imgs.append({"file": os.path.basename(im), "dhash": f"{dhash(path):016x}", "role": p["role"]})
                except Exception:  # noqa: BLE001  unreadable image: skip
                    pass
        if p.get("text") and len(p["text"]) > 200:
            texts.append({"role": p["role"], "hash": text_hash(p["text"]), "sketch": sketch(p["text"])})
    chain = case.get("technical_summary", {}).get("redirect_chain", [])
    urls = [re.sub(r"\?.*$", "", chain[-1])] if chain else []
    return {"images": imgs, "texts": texts, "urls": urls}


def find_duplicates(fp: Dict[str, Any], others: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for cid, o in others.items():
        reasons = []
        for a in fp["images"]:
            for b in o["images"]:
                d = hamming(int(a["dhash"], 16), int(b["dhash"], 16))
                if d <= IMAGE_MAX_DISTANCE:
                    reasons.append(f"near-identical image ({d}/64 bits differ)")
                    break
            else:
                continue
            break
        for a in fp["texts"]:
            for b in o["texts"]:
                if a["hash"] == b["hash"]:
                    reasons.append("identical page text")
                elif sketch_jaccard(a["sketch"], b["sketch"]) >= TEXT_NEAR_DUP:
                    reasons.append("near-identical page text")
                else:
                    continue
                break
            else:
                continue
            break
        if fp["urls"] and fp["urls"] == o["urls"]:
            reasons.append("same final URL")
        if reasons:
            out.append({"case": cid, "reasons": list(dict.fromkeys(reasons))})
    return out


def load_fingerprints(cases_dir: str = None) -> Dict[str, Dict[str, Any]]:
    """Fingerprints of all cases that have a case_input.json (cached on disk, keyed by file mtime)."""
    cases_dir = cases_dir or os.path.join(DATA, "cases")
    cache: Dict[str, Any] = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except ValueError:
            cache = {}
    out, dirty = {}, False
    for cid in sorted(os.listdir(cases_dir)):
        f = os.path.join(cases_dir, cid, "case_input.json")
        if not os.path.exists(f):
            continue
        stamp = os.path.getmtime(f)
        if cache.get(cid, {}).get("stamp") == stamp:
            out[cid] = cache[cid]["fp"]
            continue
        out[cid] = fingerprint(json.load(open(f, encoding="utf-8")))
        cache[cid] = {"stamp": stamp, "fp": out[cid]}
        dirty = True
    if dirty:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    return out
