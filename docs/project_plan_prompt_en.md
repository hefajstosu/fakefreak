# Project plan: fake news detection and ad grouping using alternative versions

## 1. Context and core concept
Our goal is to build a system for classifying and grouping ads (including fake news detection) based on an extended database that contains both original content and modified, alternative versions of it.

Note: the source ads used for testing are in Polish. All prompts and analytical output are in English; verbatim ad text and entity names stay in Polish.

---

## 2. Key functional requirements

### 2.1. Database and generation of alternative versions
* The database stores original examples of fake news/ads and **alternative versions** generated from them.
* Alternative versions are created by modifying selected content attributes (e.g., the person shown, car brand, the impersonated company, the apparent skin color / hair color / gender / age of unidentified people).
* **Dynamic configuration of changes:** the number and scope of modified features are not fixed. They must be dynamic and tunable during the testing phase (parameters: N variants, mutation depth k, allowed slots, replacement pools).
* Demographic traits of unidentified people ARE generated as alternatives, but are stored in a separate non-grouping bucket and have zero weight in grouping (see 2.3).

### 2.2. Similarity classification and grouping of new ads
* When classifying a new ad, the model compares its similarity with all records in the database, both originals and alternative versions.
* Based on the computed similarity, the system creates **ad groups (clusters)**.
* **Overlapping groups:** ad groups may overlap to some degree (one ad can belong to more than one group).
* **Handling new cases:** if the analyzed ad is not similar enough to any existing entry or group, the system creates a **new ad group** from it.

### 2.3. Feature relevance in grouping
The system must distinguish relevant features from irrelevant (or sensitive) ones to avoid incorrect or harmful grouping:
* **Relevant features (should influence grouping):** e.g., the advertised company/brand, the main goal of the ad, the message.
* **Irrelevant features (must not determine groups):** demographic or superficial traits such as skin color (creating a group of ads only for white people makes no sense).
* **Why alternatives include demographics:** variants that differ only in non-grouping traits teach and test the invariance. Their canonical text and all grouping fields stay identical to the parent, and the test is that they cluster with the parent.

---

## 3. Task
Based on the above:
1. **Develop a complete, detailed action plan (roadmap) for implementing this project step by step.**
2. **Take into account all relevant aspects** (including data architecture, model selection, similarity metrics, feature selection, testing, potential risks, and technical and ethical challenges).

---

## 4. Additional implementation notes (added after prompt review)
* **Variants are synthetic.** Flag them (`synthetic: true`, `parent_ad_id`) and never publish them.
* **Evaluation leakage:** a variant must always be in the same train/test split as its parent, otherwise test results are inflated.
* **Programmatic validation** of every generated variant (see `validate_variants.py`): locked fields identical, exactly k slots mutated, no duplicates, URLs preserved, demographics-only variants leave the canonical text unchanged.
* **Visual layer** is outside the LLM prompts: perceptual hash / CLIP vector of the whole creative, with light augmentations (face masking, contrast, crop).
* **Face recognition:** the LLM never identifies faces. Unnamed people are flagged and resolved by a local module (DeepFace) before alternative generation.
* **Unit of analysis is a case,** not a single file: ad creative + bridge page + offer page (+ decoy page) + network logs. The extraction prompt takes labeled parts and decides the scam type from where the funnel ends.
* **Preprocessing pipeline (code, not LLM):**
  * `har_to_technical_summary.py`: HAR files -> tracker IDs, redirect chain, form endpoints, first-party file names, utm values. Mass infrastructure filtered; no cookies, bodies or IPs kept.
  * `video_to_case_inputs.py`: video -> Polish transcript (faster-whisper) + 2x2 contact sheet of 4 non-blank, non-duplicate keyframes. Optional crop of the OS status bar or a region of interest for screen recordings.
  * `face_identity_module.py`: DeepFace matching against a curated public-figure reference set -> `[RESOLVED_IDENTITIES]`. Its category map also produces same-category replacement pools for the alternatives prompt.
* **Two templates per case:** the ad creative template and the landing page template are separate locked features; persuasion devices are a separate medium-weight feature.
* **Cross-case hard anchors seen in the sample data:** the same session-tracking API paths (`/api/v1/trigger/field/<uuid>/`, `/api/v1/agent/persist-session-record/`) appear on several unrelated-looking domains. Treat such first-party endpoint patterns as technical anchors.
* **Closed vocabularies** (scam type, topic, role, creative template) keep labels consistent across ads; extend the lists as new campaign types appear.
