"""The contracts between the pipeline stages (schemas/*.schema.json) and the technical keys that code owns."""
import json
import os
from functools import lru_cache
from typing import Any, Dict, List

from jsonschema import Draft7Validator

from .paths import SCHEMAS

# technical_summary (case_input) = technical_artifacts (profile) minus ad_library_metadata; written by code only
TECH_KEYS = ["urls_and_domains", "redirect_chain", "tracker_ids", "dom_and_form_clues", "domain_and_cert_metadata"]


def empty_tech() -> Dict[str, List[Any]]:
    return {k: [] for k in TECH_KEYS}


@lru_cache(maxsize=None)
def validator(schema_file: str) -> Draft7Validator:
    with open(os.path.join(SCHEMAS, schema_file), encoding="utf-8") as f:
        return Draft7Validator(json.load(f))


def errors(obj: Any, schema_file: str, limit: int = 150) -> List[str]:
    """'path: message' for every violation (message cut to `limit` characters)."""
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:limit]}"
            for e in validator(schema_file).iter_errors(obj)]


def check(obj: Any, schema_file: str, what: str) -> None:
    errs = errors(obj, schema_file)
    if errs:
        raise ValueError(f"{what} invalid: " + "; ".join(errs[:5]))
