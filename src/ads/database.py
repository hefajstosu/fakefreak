"""The case database: one folder per case in data/cases (gitignored).

    ids = case_ids("manifest.json")            # sorted ids of the cases that have this file
    profiles = load_profiles()                 # {case id: profile}; duplicates of another case are left out
    meta = case_meta(cid)                      # meta.json of a case saved from the panel
    path = first_image(cid)                    # its first screenshot or video contact sheet
    cid = save_case(case, profile, decision)   # store an analysed article as web_<n>
"""
import glob
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

from .paths import CASES, DATA

NO_CASES = ("No case profiles found in {}/*/profile.json. Put the per-case files there (README, 'Sample data') "
            "or analyse and save new material in the web panel first.")


def case_ids(required: str = "profile.json", cases_dir: Optional[str] = None) -> List[str]:
    cases_dir = cases_dir or CASES
    return sorted(c for c in os.listdir(cases_dir) if os.path.exists(os.path.join(cases_dir, c, required)))


def case_meta(cid: str, cases_dir: Optional[str] = None) -> dict:
    """data/cases/<id>/meta.json written by the panel: {"status": "unconfirmed", "duplicate_of": id, ...} or {}."""
    f = os.path.join(cases_dir or CASES, cid, "meta.json")
    try:
        return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    except ValueError:
        return {}


def load_profiles(cases_dir: Optional[str] = None) -> Dict[str, dict]:
    cases_dir = cases_dir or CASES
    out = {}
    for f in glob.glob(os.path.join(cases_dir, "*", "profile.json")):
        cid = os.path.basename(os.path.dirname(f))
        if not case_meta(cid, cases_dir).get("duplicate_of"):  # a duplicate belongs to its original
            out[cid] = json.load(open(f, encoding="utf-8"))
    return out


def require_profiles(profiles: Dict[str, dict], cases_dir: Optional[str] = None) -> Dict[str, dict]:
    """The profiles, or exit with a clear message when the database is empty (metrics need cases)."""
    if not profiles:
        sys.exit(NO_CASES.format(cases_dir or CASES))
    return profiles


def first_image(cid: str) -> Optional[str]:
    """Absolute path of the case's first screenshot or video contact sheet, if any."""
    f = os.path.join(CASES, cid, "case_input.json")
    if not os.path.exists(f):
        return None
    for part in json.load(open(f, encoding="utf-8"))["parts"]:
        for img in part.get("images", []):
            path = img if os.path.isabs(img) else os.path.join(DATA, img)
            if os.path.exists(path):
                return path
    return None


def save_case(case: Dict[str, Any], profile: Dict[str, Any], dec: Optional[Dict[str, Any]] = None,
              cases_dir: Optional[str] = None) -> str:
    """Store an analysed article as <cases_dir>/web_<n>/ (screenshots copied in) so later articles are compared
    with it. New and uncertain cases are marked unconfirmed until an analyst confirms them."""
    cases_dir = cases_dir or CASES
    n = 1
    while os.path.exists(os.path.join(cases_dir, f"web_{n}")):
        n += 1
    cid = f"web_{n}"
    d = os.path.join(cases_dir, cid)
    os.makedirs(d)
    case = json.loads(json.dumps(case))
    case["case_id"] = cid
    for part in case["parts"]:
        saved = []
        for img in part.get("images", []):
            shutil.copy(img, os.path.join(d, os.path.basename(img)))
            saved.append(f"cases/{cid}/{os.path.basename(img)}")
        part["images"] = saved
    status = (dec or {}).get("status")
    meta: Dict[str, Any] = {"decision": status}
    if status == "duplicate":
        meta["duplicate_of"] = dec["join"][0]
    elif status in ("new_unconfirmed", "suggested_family", "likely"):
        meta["status"] = "unconfirmed"
    for name, data in (("case_input.json", case), ("profile.json", profile), ("meta.json", meta)):
        json.dump(data, open(os.path.join(d, name), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return cid
