"""Live URL scan: fetch a landing page the way a phone user would and extract the same technical traces
that `har.py` extracts from recorded network logs, so a freshly scanned URL can be compared with the database.

    from ads.preprocess.url_scan import scan_url
    r = scan_url("https://example.com/")
    r["ok"], r["final_url"], r["text"], r["technical_summary"], r["notes"]

What it does
  * follows HTTP redirects, `<meta refresh>` and (for near-empty pages) simple absolute JS redirects, recording the chain;
  * sends a mobile user agent, Polish locale and a social-media referer, because scam pages often show reviewers
    a neutral page (cloaking) and the real one only to such visitors;
  * extracts tracker IDs (Meta Pixel, GTM, GA, Google Ads, TikTok), form endpoints with field names, and distinctive
    first-party script/style file names, in the same string formats as `har.py`.
What it does NOT do: execute JavaScript, solve captchas, or log in. JS-rendered pages give little text (a note says so).

Safety: only http/https; every hop is resolved and refused if it points to a private, loopback, link-local or reserved
address (so the demo cannot be used to probe the local network); 15 s timeout; response size capped at 3 MB.
Never scan a suspected scam domain from a machine you care about without a clean network context: the page is only
downloaded and parsed as text, never rendered or executed.
"""
import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import requests

from . import har as harmod
from .assemble import html_str_to_text

UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Mobile Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5", "Referer": "https://l.instagram.com/",
           "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"}
MAX_BYTES = 3_000_000
MAX_HOPS = 8
TIMEOUT = 15

META_REFRESH = re.compile(r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]*content=["\']?\s*\d+\s*;\s*url=([^"\'>\s]+)', re.I)
JS_REDIRECT = re.compile(r'(?:window\.|document\.|top\.)?location(?:\.href|\.replace\()?\s*[=(]\s*["\']((?:https?:)?//[^"\']+)["\']', re.I)
TRACKERS = [
    ("meta_pixel", re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})['\"]")),
    ("meta_pixel", re.compile(r"facebook\.com/tr/?\?[^\"'\s>]*?\bid=(\d{6,})")),
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
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
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
    base = harmod.reg_domain(urlsplit(base_url).hostname or "")
    out: List[str] = []
    for src in ASSET.findall(html):
        u = urlsplit(urljoin(base_url, src))
        if harmod.reg_domain(u.hostname or "") != base or harmod.is_mass(u.hostname or ""):
            continue
        name = u.path.rsplit("/", 1)[-1]
        if name and f"file:{name}" not in out:
            out.append(f"file:{name}")
    return out


def _read(resp: requests.Response) -> str:
    chunks, size = [], 0
    for chunk in resp.iter_content(65536):
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BYTES:
            break
    raw = b"".join(chunks)
    return raw.decode(resp.encoding or resp.apparent_encoding or "utf-8", errors="replace")


def scan_url(url: str, allow_private: bool = False) -> Dict[str, Any]:
    notes: List[str] = []
    chain: List[str] = []
    cur, html, status = url.strip(), "", None
    session = requests.Session()
    try:
        for _ in range(MAX_HOPS):
            why = _blocked(cur, allow_private)
            if why:
                return {"ok": False, "error": why, "chain": chain}
            r = session.get(cur, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True)
            chain.append(cur)
            status = r.status_code
            loc = r.headers.get("Location")
            if 300 <= status < 400 and loc:
                cur = urljoin(cur, loc)
                continue
            html = _read(r)
            nxt = None
            m = META_REFRESH.search(html)
            if m:
                nxt = urljoin(cur, m.group(1))
            elif len(html_str_to_text(html)) < 300:  # near-empty page: maybe a JS redirect stub
                j = JS_REDIRECT.search(html)
                if j:
                    nxt = urljoin(cur, j.group(1))
            if nxt and nxt not in chain:
                notes.append("followed a meta-refresh/JS redirect")
                cur = nxt
                continue
            break
        else:
            notes.append(f"stopped after {MAX_HOPS} hops")
    except requests.RequestException as e:
        return {"ok": False, "error": f"request failed: {str(e)[:160]}", "chain": chain}

    text = html_str_to_text(html)
    if len(text) < 200:
        notes.append("very little text: the page may be rendered by JavaScript or cloaked (not executed here)")
    if status and status >= 400:
        notes.append(f"HTTP status {status}")
    title = TITLE.search(html)
    pub_chain = [harmod.sanitize_url(u) for u in chain if not harmod.is_mass(urlsplit(u).hostname or "")]
    tech = {
        "urls_and_domains": [harmod.sanitize_url(cur)],
        "redirect_chain": pub_chain,
        "tracker_ids": extract_trackers(html),
        "dom_and_form_clues": extract_forms(html, cur) + extract_first_party_files(html, cur),
        "domain_and_cert_metadata": [],
    }
    return {"ok": True, "final_url": cur, "status": status, "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None,
            "text": text, "technical_summary": tech, "notes": notes}
