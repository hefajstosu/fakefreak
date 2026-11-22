# Methodology: linking scam ads into campaigns

Task: "Follow the Fake" (HackNation 2026, NASK). Goal: from a pile of seemingly independent scam ads, find the shared
traces that tie them into campaigns, and tell whether a new item belongs to a known campaign or starts a new one. The
goal is explicitly not a fake/real classifier for a single ad.

## 1. Approach in one paragraph
Each ad **case** (ad screenshot or video, the pages it leads to, recorded or live network traces) is turned into a
structured **profile** by a multimodal LLM under a strict schema. Profiles are compared with a transparent weighted
similarity plus hard-evidence rules (tracker IDs, shared platform endpoints, domains, sender page). New items get a
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
| Excluded | demographics of unidentified people, screenshot artefacts, mass infrastructure | zero weight by design |

Demographics of unidentified people are recorded in a separate bucket that similarity never reads, so a variant that
changes only those traits must score exactly 1.0 against its parent. This is checked automatically.

## 4. Extraction
- Closed vocabularies (scam type, topic, role, templates, persuasion devices) keep labels consistent across ads.
- The model is told to be precise about entity lists and to identify people only from text or captions, never from
  faces. Unnamed people are flagged for an optional local face-matching step (not installed in this build).
- **Code owns what code can know:** technical traces, funnel stages and page text are written by code, not typed by the
  model. This removed a class of malformed-JSON failures and means traces are never hallucinated.
- Output is validated against the profile schema, with one repair attempt; transcripts of video audio come from the
  LLM's audio input.

## 5. Similarity and evidence
`similarity.score(a, b)` (a thin wrapper over `src/ads/sim_functions/`) returns a score, per-feature contributions, the
features that could not be compared, and the strong links. The score is a weighted mean over the features present on
both sides (null-aware: a feature missing on one side is skipped, not counted as zero); technical anchors (tracker IDs,
redirect domains, endpoint and form clues, sponsoring page) are features with their own weights. Hard evidence does not
change the number. It is reported next to it and, in grouping, a shared tracker ID, two or more shared platform endpoint
prefixes or the same sponsoring page are must-links: they join two cases whatever their score. Shared domains and files
are supporting evidence only (a mass domain must not chain unrelated campaigns).

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
`src/ads/explain.py` recomputes each explanation with the same functions, weights and anchor settings as the score,
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
Explaining the sample pairs also surfaced a limit of the score itself: platform endpoints that make a must-link are
compared as raw, host-specific strings inside the score, so they can add nothing to the number while still joining
the pair as evidence. The explanation shows this rather than hiding it.

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
- Placeholder similarity at threshold 0.6: 6 of 7 ranking constraints; broad pairwise precision 1.00 and recall 0.46;
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
- 35 automated tests (synthetic data only) cover schemas, extraction post-processing, scanning, similarity, dedup,
  decisions, robustness and model failover.

### Quality on new material (`python -m ads.quality`, no LLM calls, about 2 s)
The organiser tests new variants of known campaigns and material from other campaigns. `ads.quality` replays that:
every item is analysed against the database exactly as in the panel (`analyze.compare`) and its outcome is checked
against the gold labels: correct, missed (a known campaign was not joined) or false join (joined a campaign it has no
gold relation to). Items: each real case left out of the database in turn, and the 189 synthetic variants (surface
details swapped, scam blueprint kept) as new versions of known campaigns, with the parent in the database or held
out, and with the parent's technical traces (same operator) or without them (new infrastructure). Tau 0.6:

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
is not linked by content alone. The next steps are entity overlap as supporting rather than subtracting evidence and
the E5 embeddings for the free-text features, both checked against this table.

## 11. Ethics, legal and data handling
- No face identification by the LLM; demographics never influence grouping; variants about real people are internal
  synthetic data.
- The organiser's sample data is not redistributed: it and everything derived from it are gitignored; the repository
  holds code, schemas, prompts, a label-only gold file and synthetic tests.
- Free-tier LLM inputs may be used by the provider to improve its products; this is noted for any real deployment.
- Dependency licences are listed in `docs/LICENSES.md` (to be verified before submission).

## 12. Limitations and next steps
Small labelled set and guessed weights; a stronger similarity (semantic embeddings, rarity-weighted evidence,
entity overlap as supporting evidence only) is the biggest lever. Image duplicates miss differently framed captures.
The URL scan does not run JavaScript. No face reference set yet. Per-campaign calibrated thresholds, an ad-library
scheduler and a graph database are future work.

## 13. Reproduce
See `README.md` (setup, commands) and `CLAUDE.md` (operational notes such as free-tier quota). Demo script: `docs/DEMO.md`.
