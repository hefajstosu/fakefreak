"""Extraction: case_input.json -> profile.json (schemas/profile.schema.json).

    python -m ads.llm.extract case_input.json profile.json [--model gemini-3.5-flash]

Steps: build the labeled message from the case parts, call the LLM with prompts/extraction.txt,
validate against the profile schema (one repair retry on errors), then overwrite the
technical_artifacts fields with the code-parsed values so traces are never LLM-written.
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List

from jsonschema import Draft7Validator

from ..paths import DATA, PROMPTS, SCHEMAS
from .client import LLMClient, Part, make_client

PROMPT_PATH = os.path.join(PROMPTS, "extraction.txt")
SCHEMA_PATH = os.path.join(SCHEMAS, "profile.schema.json")
LABEL = {"ad_creative": "[AD_CREATIVE]", "bridge_page": "[BRIDGE_PAGE]",
         "offer_page": "[OFFER_PAGE]", "decoy_page": "[DECOY_PAGE]"}
ORDER = ["ad_creative", "bridge_page", "offer_page", "decoy_page"]
PAGE_CHARS = 6000  # per page part; longer pages keep their beginning and are marked with [...]
TECH_KEYS = ["urls_and_domains", "redirect_chain", "tracker_ids", "dom_and_form_clues",
             "domain_and_cert_metadata"]


def build_parts(case: Dict[str, Any]) -> List[Part]:
    parts: List[Part] = [("text", f"Case ID: {case['case_id']}\nAnalyze the following case and return the JSON profile.")]
    for role in ORDER:
        for p in (x for x in case["parts"] if x["role"] == role):
            parts.append(("text", LABEL[role]))
            if p.get("text"):
                parts.append(("text", p["text"]))
            if p.get("transcript"):
                parts.append(("text", "[VIDEO_TRANSCRIPT]\n" + p["transcript"]))
            for img in p.get("images", []):
                parts.append(("image", os.path.join(DATA, img)))
    parts.append(("text", "[TECHNICAL_SUMMARY]\n" + json.dumps(case["technical_summary"], ensure_ascii=False)))
    parts.append(("text", "[RESOLVED_IDENTITIES]\n" + json.dumps(case["resolved_identities"], ensure_ascii=False)))
    return parts


def schema_errors(profile: Dict[str, Any]) -> List[str]:
    v = Draft7Validator(json.load(open(SCHEMA_PATH, encoding="utf-8")))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in v.iter_errors(profile)]


def enforce_technical(profile: Dict[str, Any], case: Dict[str, Any]) -> None:
    """Technical traces come from code, not from the model."""
    ta = profile.setdefault("technical_artifacts", {})
    for k in TECH_KEYS:
        ta[k] = case["technical_summary"][k]
    ta.setdefault("ad_library_metadata", {"page_id_or_name": None, "payer_name": None, "dates_active": None})


def assemble_text(creative_text: str, case: Dict[str, Any]) -> str:
    """extracted_text_verbatim = the model's OCR of the creative + page text and transcripts from code."""
    nl = chr(10)
    out = ["[[AD_CREATIVE]]" + nl + (creative_text or "").strip()]
    for role in ORDER[1:]:
        for p in (x for x in case["parts"] if x["role"] == role and x.get("text")):
            t = p["text"]
            out.append(f"[[{role.upper()}]]" + nl + (t if len(t) <= PAGE_CHARS else t[:PAGE_CHARS].rsplit(" ", 1)[0] + " [...]"))
    for p in case["parts"]:
        if p.get("transcript"):
            out.append("[[VIDEO_TRANSCRIPT]]" + nl + p["transcript"])
    return nl.join(out)


def enforce_funnel(profile: Dict[str, Any], case: Dict[str, Any]) -> None:
    """Funnel stages are known from the case parts, so code sets them instead of the model."""
    roles = {p["role"] for p in case["parts"]}
    stages = [s for s, r in (("ad", "ad_creative"), ("bridge_page", "bridge_page"),
                             ("offer_page", "offer_page"), ("decoy_page", "decoy_page")) if r in roles]
    profile.setdefault("visual_and_production", {})["funnel_stages"] = stages


def finalize(profile: Dict[str, Any], case: Dict[str, Any]) -> None:
    profile["extracted_text_verbatim"] = assemble_text(profile.get("extracted_text_verbatim", ""), case)
    enforce_technical(profile, case)
    enforce_funnel(profile, case)


def _generate(client: LLMClient, system: str, parts: List[Part], use_cache: bool) -> Dict[str, Any]:
    try:
        return client.generate_json(system, parts, use_cache)
    except ValueError as e:  # malformed JSON: ask once more, bypassing the cache
        retry = parts + [("text", f"Your previous reply was not valid JSON ({e}). Return the complete JSON profile again, "
                                  "with all strings correctly escaped.")]
        return client.generate_json(system, retry, use_cache=False)


def extract(case: Dict[str, Any], client: LLMClient, use_cache: bool = True) -> Dict[str, Any]:
    system = open(PROMPT_PATH, encoding="utf-8").read()
    parts = build_parts(case)
    profile = _generate(client, system, parts, use_cache)
    finalize(profile, case)
    errors = schema_errors(profile)
    if errors:  # one repair attempt, showing the model its own errors
        repair = parts + [("text", "Your previous JSON was invalid:\n" + "\n".join(errors[:15]) +
                           "\nPrevious JSON:\n" + json.dumps(profile, ensure_ascii=False) +
                           "\nReturn the corrected full JSON profile only.")]
        profile = _generate(client, system, repair, use_cache)
        finalize(profile, case)
        errors = schema_errors(profile)
    if errors:
        raise ValueError("profile still invalid after repair:\n" + "\n".join(errors[:15]))
    return profile


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_input")
    ap.add_argument("out")
    ap.add_argument("--model", default=None)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    case = json.load(open(a.case_input, encoding="utf-8"))
    client = make_client(**({"extraction_model": a.model} if a.model else {}))
    profile = extract(case, client, use_cache=not a.no_cache)
    json.dump(profile, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"ok: {a.out} ({profile['core_narrative']['ad_goal_scam_type']})")


if __name__ == "__main__":
    sys.exit(main())
