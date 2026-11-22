"""preprocess/domain_meta.py with every network call mocked: facts, cache, mass-infrastructure filter, evidence."""
from datetime import date

import pytest

from ads.preprocess import domain_meta as dm
from ads import clustering
from ads.similarity import score
from factory import make


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


def fake_web(calls):
    def get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if url.startswith("https://rdap.org/domain/"):
            d = url.rsplit("/", 1)[1]
            if d == "gone.test":
                return Resp(None, 404)
            return Resp({"events": [{"eventAction": "registration", "eventDate": "2026-10-08T10:00:00Z"}],
                         "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Reg Inc"]]]}],
                         "status": ["client transfer prohibited"],
                         "nameservers": [{"ldhName": "ns1.own-dns.test"}, {"ldhName": "a.ns.cloudflare.com"}]})
        if url.startswith("https://dns.google/"):
            return Resp({"Status": 3} if params["name"] == "gone.test" else
                        {"Status": 0, "Answer": [{"type": 1, "data": "10.0.0.1" if params["name"] == "lan.test"
                                                  else "104.16.0.1"}]})
        if url.startswith("https://rdap.org/ip/"):
            return Resp({"name": "CLOUDFLARENET", "country": "US"})
        if "certspotter" in url:
            return Resp([{"dns_names": [params["domain"], "www." + params["domain"], "sister.test"],
                          "not_before": "2026-10-08T00:00:00Z", "issuer": {"friendly_name": "Let's Encrypt"}}])
        if "web.archive.org" in url:
            return Resp([["timestamp"], ["20261009000000"]])
        if "hole.cert.pl" in url:
            r = Resp(None)
            r.text = "listed.test\nfoo.example\n"
            return r
        raise AssertionError(url)
    return get


@pytest.fixture
def web(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(dm, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(dm.requests, "get", fake_web(calls))
    monkeypatch.setattr(dm.time, "sleep", lambda s: None)
    monkeypatch.setattr(dm, "_warning_list", None)
    return calls


def test_domain_facts_from_every_source(web):
    f = dm.domain_facts("site.test", captured=date(2026, 10, 9))
    assert {"domain:site.test", "registered:2026-10-08", "registrar:Reg Inc", "ns:own-dns.test", "ns:cloudflare.com",
            "net:CLOUDFLARENET", "certs:1", "cert_san:sister.test", "wayback_first:2026-10-09",
            "regbatch:2026-10-08|Reg Inc", "age_at_capture_days:1"} <= set(f)


def test_answers_are_cached_and_missing_domains_are_reported(web):
    dm.domain_facts("site.test")
    n = len(web)
    dm.domain_facts("site.test")
    assert len(web) == n                                   # second time from the cache
    gone = dm.domain_facts("gone.test")
    assert "status:rdap_not_found" in gone and "status:nxdomain" in gone


def test_private_addresses_are_never_looked_up(web):
    dm.domain_facts("lan.test")
    assert not any(u.startswith("https://rdap.org/ip/") for u in web)


def test_only_non_mass_facts_can_link_and_a_shared_certificate_joins_a_campaign(web):
    facts = dm.domain_facts("site.test", captured=date(2026, 10, 9))
    assert dm.linking_facts(facts) == ["cert_san:sister.test", "ns:own-dns.test", "regbatch:2026-10-08|Reg Inc"]
    a, b = make(), make(product="Other", text="different words entirely here")
    a["technical_artifacts"]["domain_and_cert_metadata"] = facts
    b["technical_artifacts"]["domain_and_cert_metadata"] = ["domain:sister.test", "registrar:Other Reg"]
    r = score(a, b)
    assert any(s.startswith("domains on one certificate") for s in r["strong_links"]) and clustering.is_must_link(r)
    assert "infra_metadata" not in r["contributions"]       # weight 0: reported, not scored


def test_cert_pl_warning_list_is_checked_locally(web):
    assert "warning_list:cert_pl" in dm.domain_facts("listed.test")
    assert "warning_list:cert_pl" not in dm.domain_facts("site.test")
    assert sum("hole.cert.pl" in u for u in web) == 1          # downloaded once, then checked locally
