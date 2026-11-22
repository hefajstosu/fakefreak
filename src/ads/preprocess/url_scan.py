"""Live URL scan: fetch a landing page the way a phone user would and extract the same technical traces
that `har.py` extracts from recorded network logs, so a freshly scanned URL can be compared with the database.

    from ads.preprocess.url_scan import scan_url
    r = scan_url("https://example.com/")
    r["ok"], r["final_url"], r["text"], r["technical_summary"], r["notes"]

What it does
  * follows HTTP redirects, `<meta refresh>` and (for near-empty pages) simple absolute JS redirects, recording the chain;
  * sends a mobile user agent, Polish locale and a social-media referer, because scam pages often show reviewers
    a neutral page (cloaking) and the real one only to such visitors;
  * extracts tracker IDs (Meta Pixel, GTM, GA, Google Ads, TikTok), form endpoints with field names, distinctive
    first-party script/style file names and platform endpoint paths (`api:/api/v1/...`, also from up to 3 first-party
    scripts), in the same string formats as `har.py`;
  * fingerprints the page (structure sketch and the hashes of up to 10 first-party images, page_fp.py).
What it does NOT do: execute JavaScript, solve captchas, or log in. JS-rendered pages give little text (a note says so).

Safety: only http/https; every hop is resolved and refused if it points to a private, loopback, link-local or reserved
address (so the demo cannot be used to probe the local network); 15 s timeout; response size capped at 3 MB.
Never scan a suspected scam domain from a machine you care about without a clean network context: the page is only
downloaded and parsed as text, never rendered or executed.
"""
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import requests

from ..urls import host, is_mass, is_public_ip, reg_domain, sanitize_url
from . import page_fp
from .html_text import html_str_to_text

UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Mobile Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5", "Referer": "https://l.instagram.com/",
           "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"}
MAX_BYTES = 3_000_000
MAX_HOPS = 8
TIMEOUT = 15

IMG = re.compile(r'<img[^>]+?src=["\']([^"\'>\s]+)', re.I)
MAX_IMAGES = 10
META_REFRESH = re.compile(r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]*content=["\']?\s*\d+\s*;\s*url=([^"\'>\s]+)', re.I)
JS_REDIRECT = re.compile(r'(?:window\.|document\.|top\.)?location(?:\.href|\.replace\()?\s*[=(]\s*["\']((?:https?:)?//[^"\']+)["\']', re.I)
TRACKERS = [
    ("meta_pixel", re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})['\"]")),
    ("meta_pixel", re.compile(r"facebook\.com/tr/?\?[^\"'\s>]*?\bid=(\d{6,})")),
    ("meta_pixel", re.compile(r"signals/config/(\d{10,})")),
    ("meta_pixel", re.compile(r"(?:fb_)?pixel(?:_id)?[\"']?\s*[:=]\s*[\"']?(\d{12,})", re.I)),
    ("google_tag_manager", re.compile(r"\b(GTM-[A-Z0-9]{4,})\b")),
    ("google_tag", re.compile(r"\b((?:G|AW|GT)-[A-Z0-9]{6,})\b")),
    ("google_analytics", re.compile(r"\b(UA-\d{4,}-\d{1,3})\b")),
    ("tiktok_pixel", re.compile(r"ttq\.load\(\s*['\"]([A-Z0-9]{10,})['\"]")),
]
FORM = re.compile(r"<form\b([^>]*)>(.*?)</form>", re.I | re.S)
ACTION = re.compile(r"""\baction=["']?([^"'\s>]*)""", re.I)
FIELD = re.compile(r"""<(?:input|select|textarea)\b[^>]*?\bname=["']([^"']+)["']""", re.I)
ASSET = re.compile(r"""<(?:script[^>]+src|link[^>]+href)=["']([^"']+\.(?:js|css)(?:\?[^"']*)?)["']""", re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
API_PATH = re.compile(r"""["'`](/api/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+){0,4}/?)""")
MAX_SCRIPTS = 3
MAX_SCRIPT_BYTES = 1_500_000


def extract_api_paths(text: str) -> List[str]:
    """Platform endpoint paths written literally in HTML/JS, e.g. /api/v1/trigger/field/ (a landing-page
    platform fingerprint shared by campaigns built on the same tool). Returned as 'api:<path>'."""
    out = set()
    for m in API_PATH.finditer(text):
        p = m.group(1) if m.group(1).endswith("/") else m.group(1) + "/"
        if p.count("/") >= 3:
            out.add("api:" + p)
    return sorted(out)


def _first_party(srcs: List[str], base_url: str) -> List[str]:
    """Absolute URLs of `srcs` on the page's own registered domain (never mass infrastructure), deduplicated."""
    base = reg_domain(host(base_url))
    urls: List[str] = []
    for src in srcs:
        u = urljoin(base_url, src)
        h = host(u)
        if reg_domain(h) == base and not is_mass(h) and u not in urls:
            urls.append(u)
    return urls


def first_party_script_urls(html: str, base_url: str) -> List[str]:
    return [u for u in _first_party(ASSET.findall(html), base_url) if urlsplit(u).path.endswith(".js")][:MAX_SCRIPTS]


def first_party_image_urls(html: str, base_url: str) -> List[str]:
    return [u for u in _first_party(IMG.findall(html), base_url) if not u.lower().endswith(".svg")][:MAX_IMAGES]


def analyze(html: str, base_url: str, scripts: List[str]) -> Dict[str, List[str]]:
    """Pure analysis of a page and its first-party scripts (no network): tracker IDs and clues."""
    blob = [html] + scripts
    trackers: List[str] = []
    api: List[str] = []
    for t in blob:
        trackers += [i for i in extract_trackers(t) if i not in trackers]
        api += [i for i in extract_api_paths(t) if i not in api]
    return {"tracker_ids": trackers,
            "dom_and_form_clues": extract_forms(html, base_url) + extract_first_party_files(html, base_url) + api}


def _blocked(url: str, allow_private: bool) -> Optional[str]:
    sp = urlsplit(url)
    if sp.scheme not in ("http", "https") or not sp.hostname:
        return "only http(s) URLs with a host are allowed"
    if allow_private:
        return None
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(sp.hostname, sp.port or (443 if sp.scheme == "https" else 80))}
    except socket.gaierror:
        return f"cannot resolve {sp.hostname}"
    if not all(is_public_ip(a) for a in addrs):
        return f"{sp.hostname} resolves to a non-public address; refusing to fetch"
    return None


def extract_trackers(html: str) -> List[str]:
    out: List[str] = []
    for name, rx in TRACKERS:
        for m in rx.finditer(html):
            item = f"{name}:{m.group(1)}"
            if item not in out:
                out.append(item)
    return out


def extract_forms(html: str, base_url: str) -> List[str]:
    out: List[str] = []
    for attrs, inner in FORM.findall(html):
        a = ACTION.search(attrs)
        target = urljoin(base_url, a.group(1)) if a and a.group(1) else base_url
        sp = urlsplit(target)
        fields = sorted(set(FIELD.findall(inner)))
        clue = f"POST {sp.hostname}{sp.path or '/'}" + (f" fields={','.join(fields)}" if fields else "")
        if clue not in out:
            out.append(clue)
    return out


def extract_first_party_files(html: str, base_url: str) -> List[str]:
    out: List[str] = []
    for u in _first_party(ASSET.findall(html), base_url):
        name = urlsplit(u).path.rsplit("/", 1)[-1]
        if name and f"file:{name}" not in out:
            out.append(f"file:{name}")
    return out


def _read_bytes(resp: requests.Response, limit: int) -> bytes:
    chunks, size = [], 0
    for chunk in resp.iter_content(65536):
        chunks.append(chunk)
        size += len(chunk)
        if size >= limit:
            break
    return b"".join(chunks)


def _read(resp: requests.Response, limit: int = MAX_BYTES) -> str:
    return _read_bytes(resp, limit).decode(resp.encoding or resp.apparent_encoding or "utf-8", errors="replace")


def _next_hop(html: str, cur: str) -> Optional[str]:
    """Where a meta refresh or (on a near-empty page) a simple absolute JS redirect sends the visitor."""
    m = META_REFRESH.search(html)
    if m:
        return urljoin(cur, m.group(1))
    if len(html_str_to_text(html)) < 300:  # near-empty page: maybe a JS redirect stub
        j = JS_REDIRECT.search(html)
        if j:
            return urljoin(cur, j.group(1))
    return None


def _follow(session: requests.Session, url: str, allow_private: bool, chain: List[str], notes: List[str]):
    """Follow redirects from `url` (appending each hop to `chain`); returns (error, final URL, HTML, status)."""
    cur, html, status = url, "", None
    for _ in range(MAX_HOPS):
        why = _blocked(cur, allow_private)
        if why:
            return why, cur, "", None
        r = session.get(cur, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True)
        chain.append(cur)
        status = r.status_code
        loc = r.headers.get("Location")
        if 300 <= status < 400 and loc:
            cur = urljoin(cur, loc)
            continue
        html = _read(r)
        nxt = _next_hop(html, cur)
        if nxt and nxt not in chain:
            notes.append("followed a meta-refresh/JS redirect")
            cur = nxt
            continue
        return None, cur, html, status
    notes.append(f"stopped after {MAX_HOPS} hops")
    return None, cur, html, status


def _fetch_all(session: requests.Session, urls: List[str], allow_private: bool, read, notes=None) -> list:
    """GET each first-party URL under the same safety rules as the page; `read(response)` gives the body kept."""
    out = []
    for u in urls:
        if _blocked(u, allow_private):
            continue
        try:
            r = session.get(u, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True)
            if r.status_code == 200:
                out.append(read(r))
        except requests.RequestException:
            if notes is not None:
                notes.append(f"could not fetch script {u.rsplit('/', 1)[-1][:40]}")
    return out


def scan_url(url: str, allow_private: bool = False) -> Dict[str, Any]:
    notes: List[str] = []
    chain: List[str] = []
    session = requests.Session()
    try:
        why, cur, html, status = _follow(session, url.strip(), allow_private, chain, notes)
        if why:
            return {"ok": False, "error": why, "chain": chain}
        scripts = _fetch_all(session, first_party_script_urls(html, cur), allow_private,
                             lambda r: _read(r, MAX_SCRIPT_BYTES), notes)
        images = _fetch_all(session, first_party_image_urls(html, cur), allow_private,  # the page's own image kit
                            lambda r: _read_bytes(r, MAX_BYTES))
    except requests.RequestException as e:
        return {"ok": False, "error": f"request failed: {str(e)[:160]}", "chain": chain}

    text = html_str_to_text(html)
    if len(text) < 200:
        notes.append("very little text: the page may be rendered by JavaScript or cloaked (not executed here)")
    if status and status >= 400:
        notes.append(f"HTTP status {status}")
    title = TITLE.search(html)
    pub_chain = [sanitize_url(u) for u in chain if not is_mass(host(u))]
    found = analyze(html, cur, scripts)
    sketch = page_fp.structure_sketch(html)
    tech = {
        "urls_and_domains": [sanitize_url(cur)],
        "redirect_chain": pub_chain,
        "tracker_ids": found["tracker_ids"],
        "dom_and_form_clues": found["dom_and_form_clues"],
        "domain_and_cert_metadata": [],
        "page_fingerprints": {"structure": [sketch] if sketch else [], "images": page_fp.image_hashes(images)},
    }
    return {"ok": True, "final_url": cur, "status": status, "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None,
            "text": text, "technical_summary": tech, "notes": notes}
