# Methodology: linking scam ads into campaigns

Task: "Follow the Fake" (HackNation 2026, NASK). Goal: from a pile of seemingly independent scam ads, find the shared
traces that tie them into campaigns, and tell whether a new item belongs to a known campaign or starts a new one. The
goal is explicitly not a fake/real classifier for a single ad.

## 1. Approach in one paragraph
Each ad **case** (ad screenshot or video, the pages it leads to, recorded or live network traces) is turned into a
structured **profile** by a multimodal LLM under a strict schema. Profiles are compared with a transparent weighted
similarity plus hard-evidence rules (tracker IDs and sender page join campaigns, shared platform endpoints join families
of campaigns). New items get a
**graded decision** (duplicate / same content / confirmed / likely / suggested family / new unconfirmed) with an
explanation made of the evidence that produced it. Everything is evaluated against hand-made gold labels, and the LLM
steps are validated by code, never trusted blindly.

## 2. Pipeline
```
raw material --assemble--> case_input --LLM extract--> profile --similarity--> score + evidence --decision--> status
 screenshots   page text,     (schema)    (schema,       (replaceable)   dedup, thresholds   shown in the demo
 video, HTML   HAR/URL scan,              closed enums)
 HAR logs      transcripts
```
Three JSON Schemas (`schemas/`) are the contracts between stages, so each stage can be developed and replaced on its
own: `case_input`, `profile`, `variant`.

## 3. Features and why
| Group | Examples | Role in grouping |
|---|---|---|
| Campaign core | scam type, narrative pattern, promise and mechanism | high weight; never altered by variants |
| Templates | ad creative template, landing-page template, funnel stages | high weight (the template links a campaign) |
| Persuasion devices | countdown, limited stock, fake comments, fake expert, price anchoring | medium weight; cheap for operators to reuse, so they link campaigns across products |
| Surface entities | people, product, companies, impersonated media, amounts | supporting evidence; operators swap these freely |
| Technical traces | tracker IDs, redirect chain, form and platform endpoints, first-party scripts, sender page | hard evidence, extracted by code |
| Page fingerprints | page skeleton (MinHash of tag paths and CSS classes), page image kit (hashes of large images) | extracted by code from saved pages, HAR logs and the live scan; a shared kit links a family |
| Tracking template | the operator's own tracking parameter set, ad platform campaign IDs in the funnel URLs | an own template links a family, one ad campaign ID a campaign |
| Domain and infrastructure metadata | registration date, age at capture, registrar, registration batch, name servers, hosting network, certificates and their other domains, first archive snapshot, CERT Polska warning list | public sources without keys (`docs/DATA_SOURCES.md`); reported, linking only through a registration batch or a shared certificate; CDNs never link |
| Logos and badges | channel logos, LIVE banners, AI labels on the creative | measured and explained, weight 0 (they do not separate campaigns) |
| Excluded | demographics of unidentified people, screenshot artefacts, mass infrastructure | zero weight by design |

Demographics of unidentified people are recorded in a separate bucket that similarity never reads, so a variant that
changes only those traits must score exactly 1.0 against its parent. This is checked automatically.

## 4. Extraction
- Closed vocabularies (scam type, topic, role, templates, persuasion devices) keep labels consistent across ads.
- The model is told to be precise about entity lists and to identify people only from text or captions, never from
  faces. Unnamed people stay unnamed; `preprocess/likeness.py` only reports the same face across materials.
- **Code owns what code can know:** technical traces, funnel stages and page text are written by code, not typed by the
  model. This removed a class of malformed-JSON failures and means traces are never hallucinated.
- Output is validated against the profile schema, with one repair attempt; transcripts of video audio come from the
  LLM's audio input.

## 5. Similarity and evidence
`similarity.score(a, b)` (a thin wrapper over `src/ads/sim_functions/`) returns a score, per-feature contributions, the
features that could not be compared, and the strong links. The score is a weighted mean over the features present on
both sides (null-aware: a feature missing on one side is skipped, not counted as zero); technical anchors (tracker IDs,
redirect domains, endpoint and form clues, sponsoring page) are features with their own weights. Hard evidence does not
change the number. It is reported next to it and, in grouping, a shared tracker ID, the same sponsoring page, the same
ad campaign ID or domains on one certificate are a must-link: they join two cases into one campaign whatever their
score. Two or more shared platform endpoint prefixes, two or more identical page images or the same own tracking
template prove a shared tool or kit and join two cases of the same scam type into one family (section 10). Shared
domains and files are supporting evidence only (a mass domain must not chain unrelated campaigns).

## 6. Live URL scan
For a URL, the scanner fetches the page like a phone visitor (mobile agent, Polish locale, social referer), follows HTTP,
meta-refresh and simple JS redirects, and extracts tracker IDs (also from config blobs and first-party scripts), form
endpoints, first-party files and platform endpoint paths, in the same formats as the log parser. It never executes
JavaScript, refuses private addresses, and caps size and time. Replayed offline on the saved sample pages it recovered
the same tracker and the same platform endpoints as the recorded logs, so a fresh scan can link to known cases.

## 7. Grouping, duplicates and the graded decision
- **Duplicates:** perceptual hash of images, normalised page-text hash with a near-duplicate sketch, final URL.
  Threshold 6 of 64 bits; on the sample images the closest unrelated pair was 9 bits apart. Screenshots of one ad at
  different scroll positions differ much more and are not caught (they fall through to similarity).
- **Decision statuses:** duplicate, same content on another host (same campaign, re-hosted), confirmed (score plus hard
  evidence), likely (similar content only), suggested family (related but too weak), new unconfirmed. New and uncertain
  items are stored as unconfirmed until an analyst confirms them, which limits drift from wrongly merged items.
- The graded design follows the missing-data result below: an ad shown without its landing page should suggest a
  family, not claim a campaign.

## 8. Interpretability: every link comes with its reasons
`src/ads/explain/` recomputes each explanation with the same functions, weights and anchor settings as the score,
so what the analyst reads always adds up to the number shown. It never changes a score, a group or a decision.
- **A pair of cases** (panel: "Dlaczego?" on every link; CLI: `python -m ads.explain A B`): the contribution of each
  feature and of each feature group (infrastructure, scam type and topic, templates, persuasion, entities, text, surface),
  which sum to the score; the actual values both cases share (names matched one to one with the same inflection-tolerant
  matcher as the score, shared words behind the text overlap, shared tracker IDs and domains); the values that differ and
  how much each difference cost; features skipped for missing data and on which side; the hard evidence, marked as
  joining on its own (must-link) or supporting; and a sensitivity check: the score with each feature group switched off,
  flagged when that would move the pair across the threshold. This shows whether a link rests on infrastructure, on the
  story, or on surface details that operators swap.
- **A campaign** (panel: "Dlaczego te sprawy są razem"; CLI: `--campaigns`): the rule that formed it (hard evidence
  only, hard-evidence parts merged by mean score, or mean score), its shared signature (values present in at least half of
  the members, infrastructure first, boilerplate files left out), its cohesion (weakest, mean and strongest pair and the
  member that holds on least), and the nearest other campaign with the reason it stayed separate (mean score below the
  threshold and no hard evidence, even when one pair across them is high: average link needs the mean).
- **A new article**: the rule of the graded decision that fired, with the numbers it compared (score, thresholds,
  evidence), the feature group that carries the top match and whether the decision depends on a single group; and for
  every campaign whether the article joined it, on which rule (hard evidence with which case, or mean score >= tau), or
  how far below the threshold it stayed.
- **Graph** (panel tab 03): cases coloured by campaign, framed by family, edges by kind (hard evidence, same campaign,
  related campaigns) and width by score; every edge and node opens its explanation.
- **Report**: the analyst can download the whole analysis with its reasons as Markdown.
The verdict and the grouping use one rule set: must-link evidence with any case confirms the article (before, an article
could join a campaign by hard evidence while its verdict still said "suggested family").
Explaining the sample pairs also surfaced a limit of the score itself: platform endpoints are compared as raw,
host-specific strings inside the score, so they can add nothing to the number while still linking a family as
evidence. The explanation shows this rather than hiding it.

## 9. Counterfactual variants
An LLM generates variants of a case in which surface elements are swapped (a person for another of the same category, an
outlet for another outlet, props, amounts, with Polish declension handled), while scam type, templates, persuasion
devices and technical traces stay locked. A validator checks the locked fields, the exact number of mutated slots, URL
preservation, duplicates and that text patches resolve. Variants are synthetic, flagged, never published, and always kept
with their parent to avoid evaluation leakage.

## 10. Evaluation (10 labelled cases, so indicative only)
Gold labels are hand-made: overlapping groups with strength levels (same campaign, same template, same scheme) and seven
ranking constraints of the form "similarity(a, b) must exceed similarity(a, c)".
- LLM extraction agrees with the gold scam type on 9 of 10 cases (the tenth has no matching enum value).
- The first similarity at threshold 0.6 (before the changes below): 6 of 7 ranking constraints; broad pairwise precision 1.00 and recall 0.46;
  strict F1 0.44. The failing constraint is caused by the ad-template feature being too influential.
- **Channel ablation** (each feature group switched off in turn): infrastructure and scam type + topic carry the
  grouping (strict recall 0.67 to 0.33 when either is removed). Removing text, entities or props/amounts raises recall,
  which shows that surface features dilute pairs sharing a template or infrastructure, even though operators swap exactly
  those. Removing templates fixes the failing constraint. These are the main targets for a better similarity.
- **Missing data** (LLM re-extraction from reduced inputs): pages and logs alone keep most of the signal (partner recall
  0.80 against 0.67 for the full case); the ad creative alone falls below the threshold (recall 0) yet its nearest
  neighbour is still in the right family 5 of 5 times; zero false joins in all scenarios.
- **Variants:** mean similarity to the parent 0.92 (no semantic drift); demographics-only variants score exactly 1.0
  (4 of 4); adding variants to the database made no measurable difference, which is an honest negative result on this
  small dataset with exact-match features.
- 97 automated tests (synthetic data only, no network) cover schemas, extraction post-processing, scanning, page
  fingerprints, domain metadata, similarity, grouping, explanations, dedup, decisions, the panel API and model failover.

### Quality on new material (`python -m ads.evaluation.quality`, no LLM calls, about 2 s)
The organiser tests new variants of known campaigns and material from other campaigns. `ads.evaluation.quality` replays that:
every item is analysed against the database exactly as in the panel (`analysis.compare`) and its outcome is checked
against the gold labels: correct, missed (a known campaign was not joined) or false join (joined a campaign it has no
gold relation to). Items: each real case left out of the database in turn, and the 189 synthetic variants (surface
details swapped, scam blueprint kept) as new versions of known campaigns, with the parent in the database or held
out, and with the parent's technical traces (same operator) or without them (new infrastructure). Tau 0.6, before the
endpoint decision further down (the current two-level numbers are in the last table of this section):

| test | n | correct | joined known campaign | false joins |
|---|---:|---:|---:|---:|
| leave-one-out, real cases | 10 | 0.80 | 0.67 | 0.00 |
| variants, parent known, same infrastructure | 189 | 1.00 | 1.00 | 0.00 |
| variants, parent known, new infrastructure | 189 | 0.99 (was 0.60) | 0.99 | 0.00 |
| variants, parent held out, same infrastructure | 189 | 0.80 | 0.66 | 0.00 |
| variants, parent held out, new infrastructure | 189 | 0.40 | 0.00 | 0.00 |

All 156 items that had no known campaign stayed new. Two fixes came out of this measurement; neither is a weight
change and neither moves the gold metrics (6 of 7 ranking constraints, pairwise F1 unchanged):
- Technical traces missing on one side are now dropped like every other missing feature. Before, a page without
  traces (unreachable page, ad screenshot only) was scored 0 against a case that had them, which cost about 0.12.
- A pair scoring at least 0.80 (the decision's "confirmed" level) now joins its campaign like hard evidence. Before,
  such a near-identical article was "confirmed" by the verdict but not joined, because average link compared it with
  every member of a campaign held together by hard evidence.
The open gap is the last row: a new ad of a known campaign that shares neither infrastructure nor its exact template
is not linked by content alone.

**Purity and the threshold.** `purity` is the share of the cases an item joined that are the same campaign or
template in gold (same scheme counts as wrong). `python -m ads.evaluation.quality --sweep` repeats the table for tau 0.30 to 0.80.
Lowering tau closes the last row (0.40 at 0.6, 0.80 at 0.40) with no false joins, but what it adds are same-scheme
cases: purity of known variants falls from 0.80 to 0.59. So a lower tau groups families, not campaigns; families are
handled by the hierarchy and the "suggested family" verdict, and tau stays at 0.6.

**Entities as supporting evidence** (`supporting_features` in `config/cluster.yaml`, off): people, product, companies
and outlets count when they agree and are dropped when they differ, because operators swap them on purpose. It widens
the gap between same-campaign and unrelated pairs (0.45 / 0.09 to 0.50 / 0.11) and costs nothing on any test, but at
tau 0.6 it does not move the last row, so it stays off until the team decides. With it, tau 0.30 to 0.35 gives 1.00 on
every row with no false joins, again at family-level purity (0.25 to 0.56).

**Decision: shared platform endpoints link families, not campaigns.** With endpoints as a must-link, purity on
leave-one-out was 0.33: the campaign {1, 2, 48, 61} existed only because the cases share platform endpoint paths, while
gold has {1, 2} and {48, 61} as two campaigns of one scheme. A shared landing-page tool is not proof of one operator, so
endpoints now put two cases of the same scam type into one **family** (`clustering.evidence.FAMILY_LINK`, used by
`hierarchy()`, the "suggested family" verdict and the panel), and only a shared tracker ID or sponsoring page (or a
near-identical content score) joins a **campaign**. The task asks for grouping "into campaigns or groups of similar
campaigns", so both levels are results and both are measured: campaigns against the strict gold (same campaign or
template), families against the broad gold (also same scheme).

| level | gold | P / R / F1 before | P / R / F1 now |
|---|---|---|---|
| campaigns | strict | 0.33 / 0.67 / 0.44 | **1.00** / 0.33 / **0.50** |
| families (not measured before) | broad | 1.00 / 0.85 / 0.92 | 1.00 / 0.85 / **0.92** |

New material at both levels (`ads.evaluation.quality`, tau 0.6; families: correct family or correctly none):

| test | campaigns correct | purity | false joins | families correct | family false joins |
|---|---:|---:|---:|---:|---:|
| leave-one-out, real cases | 0.60 | 1.00 | 0.00 | 0.90 | 0.00 |
| variants, parent known, same infrastructure | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 |
| variants, parent known, new infrastructure | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 |
| variants, parent held out, same infrastructure | 0.59 | 1.00 | 0.00 | 0.90 | 0.00 |
| variants, parent held out, new infrastructure | 0.56 | 1.00 | 0.00 | 0.90 | 0.00 |

Every campaign the system forms or joins is now a gold campaign (purity 1.00) and nothing is ever joined to an unrelated
case; a new ad of a known campaign with no shared trace and a different template is placed in the right family 9 times in
10. The remaining family miss is case 14 (scores 0.25 to 0.29 with its partners, just under the family threshold of
0.30); the pairs 48-61 and 14-47 ("same template" in gold) are not joined as campaigns by content alone. Both are the
target of a better text similarity: the comparison summary is matched by stem overlap only today.

### Features and sources, measured
Every feature is measured on its own against the gold labels (`python -m ads.evaluation.features`): how many cases have it, how
far it separates same-campaign pairs from unrelated ones (AUC) and how often it would mislead (unrelated pairs scoring
0.5 or more). New features were added with weights fixed by analogy before measuring (page structure as the landing
template, page images as the other first-party traces) and kept only where they did not mislead; logos and domain
metadata are measured and shown but carry weight 0. The sources behind the features, with their coverage, are in
`docs/DATA_SOURCES.md`; the patterns they revealed are in `docs/CAMPAIGN_PATTERNS.md`.

Feature usefulness on 10 cases (`python -m ads.evaluation.features`). Strict pairs per feature are few (at most 3 in the sample gold), so AUC is indicative; coverage and false hits are exact.

| feature | weight | coverage | comparable pairs | strict | same scheme | unrelated | AUC | false hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| call_to_action | 0.5 | 100% | 100% | 0.50 | 0.29 | 0.08 | 1.00 | 0/32 |
| dom_and_form_clues | 0.8 | 70% | 47% | 0.14 | 0.10 | 0.00 | 1.00 | 0/15 |
| keywords | 0.3 | 100% | 100% | 0.43 | 0.30 | 0.03 | 1.00 | 0/32 |
| landing_page_template | 0.8 | 90% | 80% | 1.00 | 1.00 | 0.00 | 1.00 | 0/25 |
| scam_type | 1.0 | 100% | 100% | 1.00 | 1.00 | 0.00 | 1.00 | 0/32 |
| url_template | 0.5 | 70% | 47% | 0.50 | 0.58 | 0.00 | 1.00 | 0/15 |
| topic | 0.5 | 100% | 100% | 1.00 | 1.00 | 0.16 | 0.92 | 5/32 |
| persuasion_devices | 0.5 | 100% | 100% | 0.62 | 0.51 | 0.33 | 0.90 | 7/32 |
| page_structure | 0.8 | 90% | 80% | 0.64 | 0.21 | 0.10 | 0.89 | 0/25 |
| featured_people | 0.8 | 90% | 100% | 0.44 | 0.18 | 0.00 | 0.83 | 0/32 |
| page_assets | 0.8 | 90% | 80% | 0.31 | 0.02 | 0.00 | 0.83 | 0/25 |
| product_name | 1.0 | 100% | 100% | 0.43 | 0.10 | 0.00 | 0.83 | 0/32 |
| impersonated_media | 0.8 | 70% | 93% | 0.67 | 0.33 | 0.12 | 0.78 | 5/30 |
| companies | 0.8 | 80% | 98% | 0.32 | 0.31 | 0.06 | 0.78 | 2/32 |
| summary | 0.8 | 100% | 100% | 0.23 | 0.23 | 0.18 | 0.76 | 0/32 |
| infra_metadata | 0.0 | 70% | 47% | 0.25 | 0.00 | 0.00 | 0.75 | 0/15 |
| promise | 0.8 | 100% | 100% | 0.27 | 0.23 | 0.10 | 0.74 | 0/32 |
| setting_and_props | 0.3 | 100% | 100% | 0.24 | 0.16 | 0.07 | 0.72 | 2/32 |
| amounts_dates_locations | 0.2 | 100% | 100% | 0.45 | 0.36 | 0.22 | 0.68 | 1/32 |
| narrative | 0.8 | 100% | 100% | 0.23 | 0.19 | 0.10 | 0.67 | 0/32 |
| funnel_stages | 0.3 | 100% | 100% | 0.44 | 0.62 | 0.47 | 0.55 | 16/32 |
| ad_library_page_name | 0.7 | 70% | 47% | 0.00 | 0.00 | 0.00 | 0.50 | 0/15 |
| redirect_chain_domains | 0.9 | 70% | 47% | 0.00 | 0.00 | 0.00 | 0.50 | 0/15 |
| ad_creative_template | 0.8 | 100% | 100% | 0.00 | 0.20 | 0.12 | 0.44 | 4/32 |
| logos_and_badges | 0.0 | 70% | 93% | 0.00 | 0.10 | 0.07 | 0.43 | 2/30 |
| tracker_ids | 1.0 | 30% | 7% | 1.00 | 0.00 | – | – | 0/0 |

Reading: content features from the LLM carry the scheme (scam type, landing template, call to action, keywords: AUC
1.00, no false hits); the new code-extracted page fingerprints and the tracking template separate as well without a
single false hit (AUC 0.83 to 1.00); persuasion devices and funnel stages describe the genre and mislead on unrelated
pairs; the ad creative template and logos do not separate campaigns at all. Domain metadata separates through the
registration batch (the gold same-campaign pair) and otherwise describes: every page sits behind one CDN. Adding the
new features left the grouping metrics unchanged (campaign precision 1.00, families F1 0.92, no false joins) while
every link now has more, and more varied, evidence behind it.

### Likeness of people: the same face in two materials (`python -m ads.preprocess.likeness`)
The task lists the likenesses of people among the features. Names already come from page text, captions and
transcripts (17 of 19 people in the samples); the open question was whether the same face links materials. Faces are
found with YuNet and compared with SFace (OpenCV Model Zoo, run by OpenCV, about 39 MB, no TensorFlow), with no names
and no reference set: same person when the cosine reaches 0.363 (OpenCV's published threshold). Measured on the samples:

| faces from | same campaign | same scheme | unrelated (false hits) |
|---|---:|---:|---:|
| ad screenshots and video frames | 0/1 | 0/5 | 1/15 |
| saved landing-page images | 2/2 | 8/8 | 4/18 |
| all | 2/3 | 8/10 | 6/32 |

The same face appears across unrelated campaigns (a public figure's likeness is reused across schemes), and the three
health videos show three different people, so a likeness describes the scheme and misleads as campaign evidence about
as often as persuasion devices do (6/32 against 7/32). It is extracted and reported, not scored. A reference set with
names (the organiser's suggestion) would only add names that the text already gives in most cases, at the cost of
identifying people biometrically; it is left out on purpose.
Face features are biometric data: computed locally, cached only in the gitignored `.cache/likeness`, never written to
profiles, the repository or the panel.

## 11. Ethics, legal and data handling
- No face identification by the LLM; demographics never influence grouping; variants about real people are internal
  synthetic data.
- The organiser's sample data is not redistributed: it and everything derived from it are gitignored; the repository
  holds code, schemas, prompts, a label-only gold file and synthetic tests.
- Free-tier LLM inputs may be used by the provider to improve its products; this is noted for any real deployment.
- Faces are compared only locally and without names (no identification); their features stay in a gitignored cache.
- Domain metadata comes from public registries and logs queried by domain name or public IP only; the scam site is
  never contacted by that module, private addresses are never looked up, and the CERT Polska list is checked locally.
- Dependency licences are listed in `docs/LICENSES.md`.

## 12. Limitations and next steps
Small labelled set and weights fixed by analogy; a stronger text similarity (semantic embeddings), rarity-weighted
evidence and entity overlap as supporting evidence only are the biggest levers. Image duplicates miss differently
framed captures. The URL scan does not run JavaScript. No face reference set, on purpose (section 10). Per-campaign
calibrated thresholds, an ad-library scheduler and a graph database are future work.

## 13. Reproduce
See `README.md` (setup, commands) and `CLAUDE.md` (operational notes such as free-tier quota). Demo script: `docs/DEMO.md`.
