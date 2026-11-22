"""The synthetic variants of the real articles (data/cases/<id>/variants*.json, gitignored)."""
import glob
import json
import os
from typing import Dict, List

from ..llm.generate import profile_sha, variant_to_profile
from ..paths import CASES

CONTENT = ("core_narrative", "entities", "visual_and_production", "canonical_comparison_text")


def load_variants(profiles: Dict[str, dict]) -> Dict[str, List[dict]]:
    """{case id: [variant as a comparable profile]} from every variants*.json of a case (generation runs were saved
    under several names), duplicates removed. Files generated from an older version of the profile are skipped."""
    out: Dict[str, List[dict]] = {}
    for cid, parent in profiles.items():
        seen, kept = set(), []
        for f in sorted(glob.glob(os.path.join(CASES, cid, "variants*.json"))):
            data = json.load(open(f, encoding="utf-8"))
            if data.get("parent_profile_sha") not in (None, profile_sha(cid)):
                print(f"warning: {os.path.basename(f)} of case {cid} is stale (profile changed since), skipped")
                continue
            for v in (variant_to_profile(dict(parent, _case_id=cid), x) for x in data["variants"]):
                key = json.dumps({k: v.get(k) for k in CONTENT}, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    kept.append(v)
        if kept:
            out[cid] = kept
    return out
