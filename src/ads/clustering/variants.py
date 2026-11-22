"""Load the synthetic variants of the real articles (data/cases/<id>/variants*.json, gitignored)."""
import glob
import json
import os
from typing import Dict, List

from ..llm.generate import profile_sha, variant_to_profile
from ..paths import CASES


def load_variants(profiles: Dict[str, dict], name: str = "variants.json") -> Dict[str, List[dict]]:
    """{case_id: [variant as a comparable profile]} for the cases in `profiles` that have a variants file.

    Variants generated from an older version of the profile are skipped with a warning (stale).
    """
    out: Dict[str, List[dict]] = {}
    for cid, parent in profiles.items():
        f = os.path.join(CASES, cid, name)
        if os.path.exists(f):
            data = json.load(open(f, encoding="utf-8"))
            if data.get("parent_profile_sha") not in (None, profile_sha(cid)):
                print(f"warning: variants of case {cid} are stale (profile changed since generation), skipped: {name}")
                continue
            parent = dict(parent, _case_id=cid)
            out[cid] = [variant_to_profile(parent, v) for v in data["variants"]]
    return out


def load_all_variants(profiles: Dict[str, dict]) -> Dict[str, List[dict]]:
    """Every variant in every data/cases/<id>/variants*.json of a fresh parent, duplicates (same content) removed.
    Generation runs were saved under several names (variants.json, variants_a00.json ..., variants_n20.json)."""
    out: Dict[str, List[dict]] = {}
    for cid in profiles:
        seen, kept = set(), []
        for f in sorted(glob.glob(os.path.join(CASES, cid, "variants*.json"))):
            for v in load_variants({cid: profiles[cid]}, os.path.basename(f)).get(cid, []):
                key = json.dumps({k: v.get(k) for k in ("core_narrative", "entities", "visual_and_production",
                                                        "canonical_comparison_text")}, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    kept.append(v)
        if kept:
            out[cid] = kept
    return out
