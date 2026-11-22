"""Recompute the code-owned evidence of existing cases without calling the LLM.

    python -m ads.preprocess.enrich --all              # page fingerprints for every case in data/cases
    python -m ads.preprocess.enrich 48 61 --domain-meta  # also public domain and infrastructure metadata (network)

For each case it reads data/cases/<id>/manifest.json, recomputes the fields that code (never the model) owns and
writes them into both case_input.json (technical_summary) and profile.json (technical_artifacts), so profiles made
earlier gain the new evidence for free. Both files are validated against their schemas before they are written.
  page_fingerprints         page structure sketches and the page image kit (preprocess/page_fp.py)
  domain_and_cert_metadata  with --domain-meta: registration, name servers, hosting network, certificate, archive
                            (preprocess/domain_meta.py; cached in .cache/domain_meta)
"""
import argparse
import json
import os
import sys
from typing import Dict, List

from ..database import case_ids
from ..paths import CASES, DATA
from ..schema import check
from . import page_fp


def enrich_case(cid: str, domain_meta: bool = False) -> Dict[str, object]:
    d = os.path.join(CASES, cid)
    manifest = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    case = json.load(open(os.path.join(d, "case_input.json"), encoding="utf-8"))
    tech = case["technical_summary"]
    tech["page_fingerprints"] = page_fp.from_manifest(manifest, DATA)
    if domain_meta:
        from . import domain_meta as dm
        tech["domain_and_cert_metadata"] = dm.case_metadata(tech, manifest, DATA)
    check(case, "case_input.schema.json", f"case {cid} case_input")
    out = {"case": cid, "pages": len(tech["page_fingerprints"]["structure"]),
           "images": len(tech["page_fingerprints"]["images"]), "domain_meta": len(tech["domain_and_cert_metadata"])}
    pf = os.path.join(d, "profile.json")
    profile = json.load(open(pf, encoding="utf-8")) if os.path.exists(pf) else None
    if profile is not None:
        ta = profile.setdefault("technical_artifacts", {})
        ta["page_fingerprints"] = tech["page_fingerprints"]
        ta["domain_and_cert_metadata"] = tech["domain_and_cert_metadata"]
        check(profile, "profile.schema.json", f"case {cid} profile")
    json.dump(case, open(os.path.join(d, "case_input.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if profile is not None:
        json.dump(profile, open(pf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


def main(argv: List[str] = None) -> None:
    ap = argparse.ArgumentParser(description="Recompute code-owned evidence of existing cases (no LLM calls)")
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--domain-meta", action="store_true", help="also query public domain/infrastructure metadata")
    a = ap.parse_args(argv)
    ids = case_ids("manifest.json") if a.all else a.cases
    if not ids:
        sys.exit("give case ids or --all")
    for cid in ids:
        r = enrich_case(cid, a.domain_meta)
        print(f"case {r['case']}: {r['pages']} page sketches, {r['images']} page images, "
              f"{r['domain_meta']} domain/infrastructure facts")


if __name__ == "__main__":
    main()
