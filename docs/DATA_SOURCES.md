# Data sources: what each one gives, how often it works, and what it is worth

The organiser asked for an indication of useful metadata sources. This is the catalogue of every source the tool
uses, measured on the 10 sample cases (7 of them have recorded network logs or a live URL, 9 have a saved page), plus
useful sources that need an API key and were therefore not used. Usefulness of the resulting features is measured by
`python -m ads.features` (AUC of same-campaign against unrelated pairs, false hits on unrelated pairs); the table is in
`METHODOLOGY.md`.

## Sources used

| Source | Gives | Coverage on the samples | Works for dead domains | Linking value | Limits, terms |
|---|---|---|---|---|---|
| Ad creative (screenshot, video contact sheet) through the LLM | scam type, narrative, promise, call to action, keywords, people, products, outlets, templates, persuasion devices, logos and badges, sponsoring page name | 10/10 cases | yes (captured material) | high for scam type, landing template, call to action, keywords (AUC 1.00); logos and the ad template do not separate campaigns (AUC 0.43-0.44) | Gemini API terms; free tier about 20 requests a day, inputs may be used by the provider |
| Video audio, transcribed by the LLM | spoken script of video ads | the 3 video cases | yes | feeds the text features | same as above |
| Saved landing pages (HTML and their files) | page text, page structure sketch, page image kit | 9/10 cases | yes (captured) | page structure AUC 0.89 and image kit AUC 0.83, no false hits | none |
| Recorded network logs (HAR) | redirect chain, tracker IDs, form and platform endpoints, first-party files, tracking parameters, page HTML and images | 7/10 cases (11 logs) | yes (captured) | tracker IDs and endpoints are the strongest operator evidence; tracking template AUC 1.00 | IP addresses and `server` headers are all CDN (Cloudflare, Google, Meta, Fastly): useless for linking, so not used |
| Live URL scan (`url_scan.py`) | the same traces as a HAR for a URL given today, plus page structure and image kit | on demand | no | as HAR | no JavaScript executed: pixels injected at runtime are missed; cloaked pages show a decoy |
| RDAP for domains (rdap.org, the registries' structured WHOIS) | registration and expiry date, registrar, status, name servers | 7/7 cases with a domain (8/8 domains; one registry gives no registration date) | yes while the registration exists | the registration batch (same day, same registrar) linked exactly the gold same-campaign pair; registrar alone links nothing | public; rate limited (the tool caches and retries) |
| RDAP for IP addresses | hosting network name and country of the first A record | 7/7 | no (needs DNS) | none on the samples: every page is behind a CDN | public; never asked about private addresses |
| DNS over HTTPS (dns.google) | does the domain still resolve, A records | 7/7 (all still resolved) | reports NXDOMAIN | descriptive | Google Public DNS terms |
| Certificate Transparency (Cert Spotter; crt.sh as fallback) | number of certificates, first issuance, issuer, other domains on the same certificate | 5/7 cases | yes (logs are permanent) | domains on one small certificate would prove one operator (none on the samples); first issuance dates the campaign | Cert Spotter free tier without a key is rate limited; crt.sh was down (HTTP 502) during the tests |
| Wayback Machine CDX | first archived snapshot | 4/7 cases | yes | dates a page that is already gone | Internet Archive terms |
| CERT Polska warning list (hole.cert.pl) | is the domain already listed as dangerous | 2/7 cases listed | yes | confirms the material is known; links nothing | public list, downloaded at most once a day and checked locally |
| Synthetic variants (LLM) | new versions of known campaigns with swapped surface details | 189 variants of 10 cases | n/a | evaluation material only (never grouped) | synthetic data about real people: internal only |

All registry and log queries send only a domain name or a public IP address; the scam site itself is never contacted
by the metadata module. Answers are cached in `.cache/domain_meta` (7 days, negative answers too).

## Useful sources not used (need a key or an agreement)

| Source | Would give | Why not used |
|---|---|---|
| Meta Ad Library API | ads by advertiser, page ID, payer, dates active, ad text; the basis for a scheduler that finds new ads of known campaigns | needs an access token and identity verification |
| urlscan.io | rendered page with JavaScript executed, DOM, requests, screenshots, similar-page search | needs an API key; public scans would publish the scam URL |
| VirusTotal | URL and domain reputation, passive DNS, related URLs | API key, rate limits |
| SecurityTrails, DomainTools | historical DNS and WHOIS, domains on the same name server or IP | commercial |
| Shodan, Censys | services and certificates on the hosting IPs (useful behind non-CDN hosting) | API key |
| PhishTank, OpenPhish | other phishing lists | overlap with the CERT Polska list for Polish targets |

## What the measurements say about sources
- Application-level traces (tracker IDs, platform endpoints, tracking parameters, page structure and image kit) are
  where campaigns differ; network-level traces (IP, hosting network, name servers) are hidden behind CDNs.
- Domain registration data is most useful as a time signal (domain age at capture, registration batches), not as an
  identity signal.
- Content features from the LLM carry the scheme (scam type, landing template, call to action) but not the operator;
  the operator shows in the technical traces. That is why grouping has two levels: campaigns from operator evidence,
  families from the scheme.
