"""Counterfactual variants: profile.json -> variants.json   (prompts/alternatives.txt, schemas/variant.schema.json)

    python -m ads.llm.generate 48 [49 ...] [--n 3] [--k 2] [--model gemini-3.1-flash-lite]
    python -m ads.llm.generate --all

One LLM call per case returns all N variants. Output is checked against the variant schema and
llm/validate.py (locked fields, exact k, no duplicates, URLs and [[PART]] markers kept).
Invalid text patches are dropped (the structured mutations are what the similarity uses);
variants that still fail are rejected. Valid variants are also materialised as profile-shaped
dicts (`variant_to_profile`) so they can be scored exactly like real profiles.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .. import schema
from ..database import case_ids
from ..paths import CASES, PROMPTS
from . import validate as vmod
from .client import load_llm_config, make_client

PROMPT = os.path.join(PROMPTS, "alternatives.txt")


def variant_to_profile(parent: Dict[str, Any], v: Dict[str, Any]) -> Dict[str, Any]:
    """A variant as a profile: inherits the parent's technical artifacts (as the prompt promises)."""
    p = copy.deepcopy(parent)
    for k in ("core_narrative", "entities", "visual_and_production", "non_grouping_attributes",
              "canonical_comparison_text", "detected_language"):
        p[k] = copy.deepcopy(v[k])
    text, _ = vmod.resolve_text(parent["extracted_text_verbatim"], v)
    p["extracted_text_verbatim"] = text
    p["_variant_of"] = parent.get("_case_id")
    p["_synthetic"] = True
    p["_mutated_fields"] = v["mutated_fields"]
    return p


def profile_sha(case_id: str) -> str:
    """Identity of the profile a variant was generated from. Evidence that code adds later (page fingerprints, domain
    metadata; see preprocess/enrich.py) is left out: variants inherit technical artifacts and never change them, so
    enriching a profile must not make its variants stale. For a profile without that evidence this is the sha of the
    file itself, as before."""
    raw = open(os.path.join(CASES, case_id, "profile.json"), "rb").read()
    p = json.loads(raw)
    ta = p.get("technical_artifacts") or {}
    if ta.get("page_fingerprints") is None and not ta.get("domain_and_cert_metadata"):
        return hashlib.sha256(raw).hexdigest()[:16]
    ta.pop("page_fingerprints", None)
    ta["domain_and_cert_metadata"] = []
    return hashlib.sha256(json.dumps(p, ensure_ascii=False, indent=2).encode("utf-8")).hexdigest()[:16]


def _schema_errors(out: Dict[str, Any]) -> List[str]:
    """Schema violations, tagged "variant <index>: ..." when they sit inside one variant (so that variant is rejected)."""
    variants = out.get("variants") if isinstance(out.get("variants"), list) else []
    errors = []
    for e in schema.validator("variant.schema.json").iter_errors(out):
        path = list(e.absolute_path)
        inside = len(path) > 1 and path[0] == "variants" and isinstance(path[1], int) and path[1] < len(variants)
        tag = f"variant {variants[path[1]].get('variant_index')}" if inside and isinstance(variants[path[1]], dict) else "schema"
        errors.append(f"{tag}: {'/'.join(map(str, path))}: {e.message[:120]}")
    return errors


def _errors_by_variant(errors: List[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for e in errors:
        tag = e.split(":", 1)[0]
        out.setdefault(tag, []).append(e)
    return out


def drop_bad_patches(parent_text: str, v: Dict[str, Any]) -> int:
    good = [p for p in v.get("text_patches") or [] if p.get("original_span") and parent_text.count(p["original_span"]) == 1]
    dropped = len(v.get("text_patches") or []) - len(good)
    if v.get("text_patches") is not None:
        v["text_patches"] = good
    return dropped


def generate(case_id: str, n: int, k: int, model: Optional[str] = None, allowed_slots=None, tag: str = "") -> Dict[str, Any]:
    """N variants of one case, written to data/cases/<id>/variants<tag>.json. `model` overrides the configured
    generation model (and turns failover off)."""
    d = os.path.join(CASES, case_id)
    parent = json.load(open(os.path.join(d, "profile.json"), encoding="utf-8"))
    sendable = {k_: v for k_, v in parent.items() if k_ != "technical_artifacts"}
    request = {"parent_ad_id": case_id, "parent_profile": sendable, "N": n, "k": k}
    if allowed_slots:
        request["allowed_slots"] = allowed_slots
    system = open(PROMPT, encoding="utf-8").read()
    client = make_client("generation_model", **({"generation_model": model} if model else {}))
    parts = [("text", json.dumps(request, ensure_ascii=False))]

    def _norm(o):  # some models return a bare list of variants
        return {"parent_ad_id": case_id, "generation_notes": [], "variants": o} if isinstance(o, list) else o

    out = _norm(client.generate_json_retry(system, parts))
    for attempt in range(2):
        dropped = sum(drop_bad_patches(parent["extracted_text_verbatim"], v) for v in out.get("variants", []))
        errors = _schema_errors(out) + vmod.validate(parent, out, k)
        if not errors or attempt == 1:
            break
        retry = parts + [("text", "Your previous output had these problems:\n" + "\n".join(errors[:20]) +
                          "\nReturn the full corrected JSON.")]
        try:
            out = _norm(client.generate_json(system, retry, use_cache=False))
        except ValueError:  # the repair itself came back malformed: keep the first answer, drop invalid variants below
            break
    bad = _errors_by_variant(errors)
    keep, rejected = [], []
    for v in out.get("variants", []):
        vtag = f"variant {v.get('variant_index')}"
        (rejected if vtag in bad else keep).append(v)
    result = {"parent_ad_id": case_id, "parent_profile_sha": profile_sha(case_id), "model": client.model, "N": n, "k": k, "dropped_patches": dropped,
              "generation_notes": out.get("generation_notes", []), "variants": keep,
              "rejected": [{"variant_index": v.get("variant_index"), "errors": bad[f"variant {v.get('variant_index')}"][:5]}
                           for v in rejected],
              "other_errors": [e for e in errors if e.split(":", 1)[0] not in bad][:5]}
    json.dump(result, open(os.path.join(d, f"variants{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result


def main() -> None:
    cfg = load_llm_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--n", type=int, default=cfg["variants"]["N"])
    ap.add_argument("--k", type=int, default=cfg["variants"]["k"])
    ap.add_argument("--model", default=None, help="override the configured generation model (no failover)")
    ap.add_argument("--slots", default=None, help="comma-separated allowed slot IDs")
    ap.add_argument("--tag", default="", help="suffix for the output file, e.g. _demo")
    a = ap.parse_args()
    slots = a.slots.split(",") if a.slots else cfg["variants"].get("allowed_slots")
    ids = case_ids() if a.all else a.cases
    for cid in ids:
        try:
            r = generate(cid, a.n, a.k, a.model, slots, a.tag)
            print(f"case {cid}: {len(r['variants'])} valid, {len(r['rejected'])} rejected, {r['dropped_patches']} patches dropped"
                  + (f"; {r['other_errors'][:1]}" if r["other_errors"] else ""))
        except Exception as e:  # noqa: BLE001
            print(f"case {cid}: FAILED {str(e)[:200]}")


if __name__ == "__main__":
    sys.exit(main())
