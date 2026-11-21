# Dependency and service inventory

The task rules (section 4) require that the solution does not infringe third-party rights, so every component is
listed here. Licences below are from the maintainers' public listings as I know them; **verify each before the
final submission**.

| Component | Use | Licence |
|---|---|---|
| google-genai (Gemini API client) | LLM extraction and generation | Apache-2.0 |
| Gemini API (Google AI Studio free tier) | hosted model | Google API terms; free-tier inputs may be used by Google to improve its products |
| python-dotenv | load `.env` | BSD-3-Clause |
| PyYAML | config files | MIT |
| jsonschema | validate JSON against schemas | MIT |
| Pillow | image resizing | HPND (permissive) |
| opencv-python-headless | video frame sampling | Apache-2.0 |
| NumPy | numerics | BSD-3-Clause |
| Streamlit | demonstrator | Apache-2.0 |
| requests | optional URL fetch | Apache-2.0 |
| pytest | tests | MIT |
| faster-whisper (optional, not used yet) | speech to text | MIT |
| DeepFace (optional, not installed) | face matching against a small public-figure set | MIT code; model weights have their own terms, check before use |

Not used and to avoid: insightface pretrained models (non-commercial), spaCy `pl_core_news_sm` (GPL-3.0).
