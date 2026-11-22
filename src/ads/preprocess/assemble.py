"""Assemble a case: data/cases/<id>/manifest.json  ->  data/cases/<id>/case_input.json

    python -m ads.preprocess.assemble 48 [49 ...]      # case ids under data/cases/
    python -m ads.preprocess.assemble --all

manifest.json (paths relative to the repo's data/ directory, forward slashes):
{
  "case_id": "61",
  "parts": [
    {"role": "ad_creative", "images": ["raw/.../ad.png"]},
    {"role": "ad_creative", "video": "raw/.../clip.mp4", "crop_top": 0.06, "roi": null},
    {"role": "bridge_page", "html": "raw/.../page.html"},
    {"role": "offer_page",  "text_file": "raw/.../page.txt"}
  ],
  "hars": ["raw/.../a.har"],            # funnel order; may be empty
  "identities": [ ... ],                # optional manual resolved_identities
  "transcribe": false,                  # transcribe video audio via the LLM (default false)
  "transcribe_model": null              # model for transcription (default: the extraction model)
}
Roles: ad_creative | bridge_page | offer_page | decoy_page. The result is validated against
schemas/case_input.schema.json. Manifests contain file names of the organiser's samples, so
they live in the gitignored data/cases/ directory.
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List

from .. import schema
from ..database import case_ids
from ..paths import CASES, DATA
from . import har as harmod
from . import page_fp
from .html_text import MAX_TEXT, html_to_text
from . import video as videomod

def rel(path: str) -> str:
    return os.path.relpath(path, DATA).replace(os.sep, "/")


def build_part(case_dir: str, idx: int, spec: Dict[str, Any], transcribe: bool, model: str = None) -> Dict[str, Any]:
    part: Dict[str, Any] = {"role": spec["role"], "source_files": []}
    images: List[str] = list(spec.get("images", []))
    part["source_files"] += images
    text = None
    if spec.get("html"):
        text = html_to_text(os.path.join(DATA, spec["html"]))
        part["source_files"].append(spec["html"])
    if spec.get("text_file"):
        text = open(os.path.join(DATA, spec["text_file"]), encoding="utf-8").read()[:MAX_TEXT]
        part["source_files"].append(spec["text_file"])
    transcript = None
    if spec.get("video"):
        vpath = os.path.join(DATA, spec["video"])
        part["source_files"].append(spec["video"])
        roi = tuple(spec["roi"]) if spec.get("roi") else None
        samples, _dur = videomod.sample_frames(vpath, videomod.SAMPLES, spec.get("crop_top", 0.0), spec.get("crop_bottom", 0.0), roi)
        sheet = os.path.join(case_dir, f"contact_sheet_{idx}.jpg")
        videomod.make_contact_sheet(videomod.pick_keyframes(samples), sheet)
        images.append(rel(sheet))
        if transcribe:  # speech-to-text through the LLM's audio input (src/ads/preprocess/transcribe.py)
            try:
                from .transcribe import transcribe_video
                transcript = transcribe_video(vpath, os.path.join(case_dir, f"audio_{idx}.mp3"),
                                              spec.get("transcribe_model") or model) or None
            except Exception as e:  # noqa: BLE001
                part["notes"] = f"transcription failed: {str(e)[:150]}"
    part["medium"] = "video" if spec.get("video") else ("html" if spec.get("html") else
                                                        ("image" if images else "text"))
    part["text"] = text
    part["images"] = images
    part["transcript"] = transcript
    part.setdefault("notes", spec.get("notes"))
    return part


def assemble(case_id: str, domain_meta: bool = False) -> Dict[str, Any]:
    case_dir = os.path.join(CASES, case_id)
    m = json.load(open(os.path.join(case_dir, "manifest.json"), encoding="utf-8"))
    parts = [build_part(case_dir, i, s, m.get("transcribe", False), m.get("transcribe_model")) for i, s in enumerate(m["parts"])]
    tech = schema.empty_tech()
    for h in m.get("hars", []):
        harmod.process(os.path.join(DATA, h), tech)
    tech["page_fingerprints"] = page_fp.from_manifest(m, DATA)  # page structure and image kit (code-owned)
    if domain_meta:  # public registration, hosting and certificate facts (network; see domain_meta.py)
        from . import domain_meta as dm
        tech["domain_and_cert_metadata"] = dm.case_metadata(tech, m, DATA)
    case = {"schema_version": "1.0", "case_id": m["case_id"], "parts": parts,
            "technical_summary": tech, "resolved_identities": m.get("identities", [])}
    schema.check(case, "case_input.schema.json", f"case {case_id}")
    json.dump(case, open(os.path.join(case_dir, "case_input.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return case


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--domain-meta", action="store_true", help="query public domain/infrastructure metadata (network)")
    a = ap.parse_args()
    ids = case_ids("manifest.json") if a.all else a.cases
    for cid in ids:
        c = assemble(cid, a.domain_meta)
        roles = [p["role"] for p in c["parts"]]
        chars = sum(len(p["text"] or "") for p in c["parts"])
        print(f"case {cid}: parts={roles} text_chars={chars} hars_urls={len(c['technical_summary']['urls_and_domains'])}"
              f" trackers={len(c['technical_summary']['tracker_ids'])}")


if __name__ == "__main__":
    sys.exit(main())
