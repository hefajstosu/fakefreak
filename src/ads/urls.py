"""URL helpers shared by the log parser, the live scan, the domain metadata and the similarity."""
import re
from typing import Iterable, List
from urllib.parse import parse_qsl, urlparse, urlsplit

# Mass infrastructure: never a campaign's own domain.
MASS_INFRA = (
    "cloudflare.com", "cloudflareinsights.com", "cdnjs.cloudflare.com", "amazonaws.com",
    "cloudfront.net", "google.com", "gstatic.com", "googleapis.com", "googleusercontent.com",
    "googletagmanager.com", "google-analytics.com", "doubleclick.net", "unpkg.com",
    "jsdelivr.net", "b-cdn.net", "bunnycdn.com", "jquery.com", "fontawesome.com",
    "facebook.com", "facebook.net", "fbcdn.net", "tiktok.com", "akamaihd.net",
    "azureedge.net", "fastly.net", "youtube.com", "ytimg.com",
)
TWO_LEVEL = ("com.pl", "org.pl", "net.pl", "co.uk")
GOOGLE_RX = re.compile(r"(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$")
KEEP_VALUE_PARAMS = ("utm_",)  # query values kept only for utm_* (campaign anchors); others become <value>


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def reg_domain(h: str) -> str:
    """Registered domain of a host name (two labels, three for com.pl-style suffixes)."""
    parts = h.split(".")
    return ".".join(parts[-(3 if ".".join(parts[-2:]) in TWO_LEVEL else 2):])


def is_mass(h: str) -> bool:
    return bool(GOOGLE_RX.search(h)) or any(h == d or h.endswith("." + d) for d in MASS_INFRA)


def sanitize_url(url: str) -> str:
    """The URL with every query value except utm_* replaced by <value> (no personal or session data)."""
    s = urlsplit(url)
    pairs = [f"{k}={v}" if k.startswith(KEEP_VALUE_PARAMS) else f"{k}=<value>"
             for k, v in parse_qsl(s.query, keep_blank_values=True)]
    return f"{s.scheme}://{s.netloc}{s.path}" + ("?" + "&".join(pairs) if pairs else "")


def domains(urls: Iterable[str]) -> List[str]:
    """Host names of a list of URLs (the first URL of a redirect entry), lowercase; non-URLs are skipped."""
    out = []
    for u in urls or []:
        h = urlparse(u if "://" in u else "//" + u).hostname
        if h and "." in h:
            out.append(h.lower())
    return out
