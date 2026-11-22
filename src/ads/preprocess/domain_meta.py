"""Public domain and infrastructure metadata for the domains of a case (no API keys; the scam site is never contacted).

    facts = domain_facts("example.com", captured=date(2026, 10, 11))
    facts = case_metadata(technical_summary, manifest, data_dir)      # every registered domain of a case

Sources, all public and free, queried only by domain name or by a public IP that DNS returned:
  RDAP (rdap.org, the registries' structured WHOIS)   registration and expiry date, registrar, status, name servers
  RDAP for IP addresses                                hosting network name and country of the first A record
  DNS over HTTPS (dns.google)                          A records (does the domain still resolve?)
  Certificate Transparency (Cert Spotter; crt.sh as a fallback)   number of certificates, first issuance, issuer,
                                                       other registered domains named on the same certificates
  Wayback Machine CDX                                  first archived snapshot (works for dead domains too)
  CERT Polska warning list (hole.cert.pl)              is the domain already on the national list of dangerous
                                                       domains (downloaded once a day, checked locally)
Every answer is cached in .cache/domain_meta (negative answers too) for CACHE_DAYS; a source that fails leaves its
facts out and the rest still count (short-lived scam domains are often gone by the time they are analysed).

Facts are strings in technical_artifacts.domain_and_cert_metadata (schema unchanged):
  domain:<d>  registered:<YYYY-MM-DD>  registrar:<name>  status:<rdap status>|nxdomain|rdap_not_found
  age_at_capture_days:<n>  regbatch:<YYYY-MM-DD>|<registrar>  ns:<provider domain>  net:<hosting network>
  country:<cc>  certs:<n>  cert_first:<YYYY-MM-DD>  cert_issuer:<org>  cert_san:<other registered domain>
  wayback_first:<YYYY-MM-DD>  warning_list:cert_pl
Mass infrastructure (big CDNs and clouds, registrar parking name servers) is marked by `is_mass_fact` and never used
as evidence: most scam pages sit behind the same CDN.
"""
import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional

import requests

from ..paths import CACHE
from ..urls import host, is_public_ip, reg_domain
from . import har

CACHE_DIR = os.path.join(CACHE, "domain_meta")
CACHE_DAYS = 7
TIMEOUT = 15
HEADERS = {"User-Agent": "follow-the-fake-research/1.0 (campaign analysis; public registry lookups)",
           "Accept": "application/json"}
MASS_NETWORKS = ("CLOUDFLARE", "AMAZON", "AWS", "GOOGLE", "FASTLY", "AKAMAI", "MICROSOFT", "AZURE", "DIGITALOCEAN",
                 "OVH", "HETZNER", "APNIC-LABS", "INCAPSULA", "SUCURI")
MASS_NS = ("cloudflare.com", "dyna-ns.net", "registrar-servers.com", "domaincontrol.com", "awsdns", "googledomains.com",
           "dns-parking.com", "namebrightdns.com", "name-services.com")
MAX_SAN = 10  # a certificate naming more domains than this is a shared CDN certificate, not one operator's


# ---------------------------------------------------------------- cached HTTP

def _cache_file(url: str, params: Optional[dict]) -> str:
    key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, key + ".json")


def get_json(url: str, params: Optional[dict] = None, timeout: int = TIMEOUT, tries: int = 2):
    """GET a JSON document with a disk cache; returns None for 404 and on failure (also cached, as {"_none": ...})."""
    f = _cache_file(url, params)
    if os.path.exists(f) and time.time() - os.path.getmtime(f) < CACHE_DAYS * 86400:
        data = json.load(open(f, encoding="utf-8"))
        return None if isinstance(data, dict) and "_none" in data else data
    result, final = None, None  # final: the source answered "no" (4xx except 429); only answers are cached
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            if 400 <= r.status_code < 500:
                final = f"http {r.status_code}"
                break
            r.raise_for_status()
            result = r.json()
            break
        except (requests.RequestException, ValueError):  # network trouble or an error page instead of JSON
            time.sleep(1)
    if result is None and final is None:
        return None  # transient: do not cache, try again next time
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(f, "w", encoding="utf-8") as out:
        json.dump(result if result is not None else {"_none": final}, out)
    return result


# ---------------------------------------------------------------- sources

def _vcard_name(entity: dict) -> Optional[str]:
    for item in (entity.get("vcardArray") or [None, []])[1]:
        if item and item[0] == "fn":
            return item[3]
    return entity.get("handle")


def rdap_domain(d: str) -> List[str]:
    j = get_json(f"https://rdap.org/domain/{d}")
    if j is None:
        return ["status:rdap_not_found"]
    facts = []
    events = {e.get("eventAction"): (e.get("eventDate") or "")[:10] for e in j.get("events", [])}
    if events.get("registration"):
        facts.append(f"registered:{events['registration']}")
    reg = next((e for e in j.get("entities", []) if "registrar" in (e.get("roles") or [])), None)
    if reg and _vcard_name(reg):
        facts.append(f"registrar:{_vcard_name(reg)}")
    facts += [f"status:{s}" for s in j.get("status", [])]
    facts += sorted({f"ns:{reg_domain(n.get('ldhName', '').lower().rstrip('.'))}" for n in j.get("nameservers", [])
                     if n.get("ldhName")})
    return facts


def dns_a(d: str) -> Optional[List[str]]:
    """A records, [] for NXDOMAIN, None when DNS could not be asked."""
    j = get_json("https://dns.google/resolve", {"name": d, "type": "A"}, timeout=10)
    if j is None:
        return None
    if j.get("Status") == 3:
        return []
    return [a["data"] for a in j.get("Answer", []) or [] if a.get("type") == 1]


def rdap_ip(ip: str) -> List[str]:
    if not is_public_ip(ip):  # never ask about private or local addresses
        return []
    j = get_json(f"https://rdap.org/ip/{ip}")
    if j is None:
        return []
    return [f for f in (f"net:{j['name']}" if j.get("name") else None, f"country:{j['country']}" if j.get("country")
                        else None) if f]


def certificates(d: str) -> List[str]:
    """Certificate Transparency: issuances for the domain and its subdomains (Cert Spotter, then crt.sh)."""
    iss = get_json("https://api.certspotter.com/v1/issuances",
                   {"domain": d, "include_subdomains": "true", "expand": ["dns_names", "issuer"]}, timeout=20)
    certs = [{"names": x.get("dns_names", []), "first": (x.get("not_before") or "")[:10],
              "issuer": ((x.get("issuer") or {}).get("friendly_name") or (x.get("issuer") or {}).get("name") or "")}
             for x in iss or []]
    if iss is None:
        crt = get_json("https://crt.sh/", {"q": d, "output": "json"}, timeout=30)
        certs = [{"names": (x.get("name_value") or "").split("\n"), "first": (x.get("not_before") or "")[:10],
                  "issuer": x.get("issuer_name") or ""} for x in crt or []]
    if not certs:
        return []
    facts = [f"certs:{len(certs)}", f"cert_first:{min(c['first'] for c in certs if c['first'])}"
             if any(c["first"] for c in certs) else None]
    facts += sorted({f"cert_issuer:{_issuer_org(c['issuer'])}" for c in certs if c["issuer"]})[:3]
    for c in certs:
        names = {reg_domain(n.lstrip("*.").lower()) for n in c["names"] if n}
        if 1 < len(names) <= MAX_SAN:
            facts += [f"cert_san:{n}" for n in sorted(names - {d})]
    return sorted({f for f in facts if f})


def _issuer_org(issuer: str) -> str:
    for part in issuer.split(","):
        if part.strip().startswith("O="):
            return part.strip()[2:].strip('"')
    return issuer.strip()[:60]


def wayback_first(d: str) -> List[str]:
    j = get_json("https://web.archive.org/cdx/search/cdx", {"url": d, "limit": 1, "output": "json", "fl": "timestamp"},
                 timeout=20)
    if not j or len(j) < 2:
        return []
    ts = j[1][0]
    return [f"wayback_first:{ts[:4]}-{ts[4:6]}-{ts[6:8]}"]


CERT_PL_LIST = "https://hole.cert.pl/domains/v2/domains.txt"
_warning_list: Optional[set] = None


def cert_pl_listed(d: str) -> List[str]:
    """Whether the domain (or a subdomain of it) is on CERT Polska's public warning list. The list is downloaded at
    most once a day into the cache and checked locally, so no single domain is sent anywhere."""
    global _warning_list
    if _warning_list is None:
        f = os.path.join(CACHE_DIR, "cert_pl_domains.txt")
        if not (os.path.exists(f) and time.time() - os.path.getmtime(f) < 86400):
            try:
                r = requests.get(CERT_PL_LIST, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=60)
                r.raise_for_status()
                os.makedirs(CACHE_DIR, exist_ok=True)
                open(f, "w", encoding="utf-8").write(r.text)
            except requests.RequestException:
                if not os.path.exists(f):
                    _warning_list = set()  # unavailable for this run; do not retry the download per domain
                    return []
        _warning_list = {ln.strip().lower() for ln in open(f, encoding="utf-8") if ln.strip()}
    listed = d in _warning_list or any(x.endswith("." + d) for x in _warning_list if x.endswith(d))
    return ["warning_list:cert_pl"] if listed else []


# ---------------------------------------------------------------- facts for a domain and for a case

def domain_facts(d: str, captured: Optional[date] = None) -> List[str]:
    facts = [f"domain:{d}"] + rdap_domain(d)
    a = dns_a(d)
    if a == []:
        facts.append("status:nxdomain")
    elif a:
        facts += rdap_ip(a[0])
    facts += certificates(d) + wayback_first(d) + cert_pl_listed(d)
    reg = next((f[11:] for f in facts if f.startswith("registered:")), None)
    registrar = next((f[10:] for f in facts if f.startswith("registrar:")), None)
    if reg and registrar:
        facts.append(f"regbatch:{reg}|{registrar}")  # domains bought the same day at the same registrar
    if reg and captured:
        try:
            facts.append(f"age_at_capture_days:{(captured - date.fromisoformat(reg)).days}")
        except ValueError:
            pass
    return facts


def case_domains(tech: Dict[str, list]) -> List[str]:
    out = []
    for u in (tech.get("urls_and_domains") or []) + (tech.get("redirect_chain") or []):
        for part in u.split(" -> "):
            h = host(part.split(" [")[0].strip())
            if h and "." in h and reg_domain(h) not in out:
                out.append(reg_domain(h))
    return out


def capture_date(manifest: Optional[dict], data_dir: Optional[str]) -> Optional[date]:
    """When the case was recorded: the first request of its first HAR log."""
    for h in (manifest or {}).get("hars", []):
        try:
            entries = har.entries(os.path.join(data_dir, h))
            first = min(e.get("startedDateTime", "") for e in entries if e.get("startedDateTime"))
            return datetime.fromisoformat(first.replace("Z", "+00:00")).date()
        except (OSError, ValueError, KeyError):
            continue
    return None


def case_metadata(tech: Dict[str, list], manifest: Optional[dict] = None, data_dir: Optional[str] = None,
                  captured: Optional[date] = None) -> List[str]:
    captured = captured or capture_date(manifest, data_dir)
    facts: List[str] = []
    for d in case_domains(tech):
        for f in domain_facts(d, captured):
            if f not in facts:
                facts.append(f)
    return facts


def today() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------- what may count as evidence

def is_mass_fact(fact: str) -> bool:
    """A hosting network or name-server provider shared by everyone (CDNs, big registrars): never a link."""
    kind, _, value = fact.partition(":")
    if kind == "net":
        return any(m in value.upper() for m in MASS_NETWORKS)
    if kind == "ns":
        return any(m in value.lower() for m in MASS_NS)
    return False


def linking_facts(facts: Iterable[str]) -> List[str]:
    """Facts that can link two cases: same registration batch, a non-mass name-server provider or hosting network,
    a domain named on the other case's certificate."""
    return sorted({f for f in facts or [] if f.startswith(("regbatch:", "ns:", "net:", "cert_san:")) and not is_mass_fact(f)})
