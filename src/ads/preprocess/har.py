"""Build a [TECHNICAL_SUMMARY] block from one or more HAR files of a single case.

Usage: python -m ads.preprocess.har out.json first.har [second.har ...]
HAR files are given in funnel order. Output follows the `technical_artifacts`
schema (minus ad_library_metadata, which comes from the ad creative).

Privacy: cookies, headers, request/response bodies and IPs are never copied.
Only URLs, tracker IDs, parameter NAMES and first-party file names are kept.
"""
import json
import re
import sys
from urllib.parse import urlsplit

from ..urls import host, is_mass, reg_domain, sanitize_url

TRACKER_PATTERNS = [
    ("meta_pixel", re.compile(r"facebook\.com/tr/?\?[^#]*?\bid=(\d{6,})")),
    ("google_ads_conversion", re.compile(r"google\.com/pagead/(?:1p-)?conversion/(\d{6,})")),
    ("google_ads_conversion", re.compile(r"googleadservices\.com/pagead/conversion/(\d{6,})")),
    ("google_analytics", re.compile(r"[?&]tid=((?:UA|G)-[A-Z0-9-]+)")),
    ("google_tag_manager", re.compile(r"googletagmanager\.com/gtm\.js\?[^#]*?\bid=(GTM-[A-Z0-9]+)")),
    ("google_tag", re.compile(r"googletagmanager\.com/gtag/js\?[^#]*?\bid=((?:G|AW|GT)-[A-Z0-9]+)")),
    ("tiktok_pixel", re.compile(r"tiktok\.com/[^\s]*?[?&]sdkid=([A-Z0-9]+)")),
]
UUID_RX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def add(lst, item):
    if item and item not in lst:
        lst.append(item)


def process(path, out):
    entries = json.load(open(path, encoding="utf-8"))["log"]["entries"]
    entries.sort(key=lambda e: e.get("startedDateTime", ""))
    page_hosts = set()
    for e in entries:
        req, res = e["request"], e["response"]
        url, h = req["url"], host(req["url"])
        mime = (res.get("content", {}).get("mimeType") or "").lower()
        status = res.get("status", 0)
        # trackers (IDs only)
        for name, rx in TRACKER_PATTERNS:
            m = rx.search(url)
            if m:
                add(out["tracker_ids"], f"{name}:{m.group(1)}")
        # HTML documents = funnel pages; redirects = chain hops
        if "html" in mime and req["method"] == "GET" and not is_mass(h):
            page_hosts.add(reg_domain(h))
            add(out["redirect_chain"], sanitize_url(url))
            add(out["urls_and_domains"], sanitize_url(url))
        if 300 <= status < 400 and not is_mass(h):
            loc = next((x["value"] for x in res.get("headers", []) if x["name"].lower() == "location"), None)
            if loc:
                add(out["redirect_chain"], f"{sanitize_url(url)} -> {sanitize_url(loc)} [{status}]")
        # form submissions: endpoint and field NAMES only
        if req["method"] == "POST" and not is_mass(h):
            names = []
            pd = req.get("postData") or {}
            if pd.get("params"):
                names = [p["name"] for p in pd["params"]]
            elif "json" in (pd.get("mimeType") or "") and pd.get("text"):
                try:
                    obj = json.loads(pd["text"])
                    names = list(obj.keys()) if isinstance(obj, dict) else []
                except ValueError:
                    pass
            clue = f"POST {h}{UUID_RX.sub('<uuid>', urlsplit(url).path)}"
            if names:
                clue += " fields=" + ",".join(names)
            add(out["dom_and_form_clues"], clue)
    # distinctive first-party JS/CSS filenames
    for e in entries:
        url = e["request"]["url"]
        h = host(url)
        fn = urlsplit(url).path.rsplit("/", 1)[-1]
        if fn.endswith((".js", ".css")) and reg_domain(h) in page_hosts and not is_mass(h):
            add(out["dom_and_form_clues"], f"file:{fn}")


def main(out_path, har_paths):
    out = {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [],
           "dom_and_form_clues": [], "domain_and_cert_metadata": []}
    for p in har_paths:
        process(p, out)
    json.dump({"technical_artifacts": out}, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
