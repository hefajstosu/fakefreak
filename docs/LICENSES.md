# Dependency and service inventory

The task rules (section 4) ask for the libraries, models and external services used, with their licences and
limits. Licences of the Python packages below were read from the installed packages' metadata (versions from
`requirements.lock`, Python 3.12, November 2026); hosted services follow their providers' terms.

| Component | Use | Licence |
|---|---|---|
| google-genai (Gemini API client) | LLM extraction and generation | Apache-2.0 |
| Gemini API (Google AI Studio free tier) | hosted model | Google API terms; free-tier inputs may be used by Google to improve its products |
| python-dotenv | load `.env` | BSD-3-Clause |
| PyYAML | config files | MIT |
| jsonschema | validate JSON against schemas | MIT |
| Pillow | image resizing | MIT-CMU (HPND, permissive) |
| opencv-python-headless | video frame sampling | Apache-2.0 |
| NumPy | numerics | BSD-3-Clause (bundled parts: 0BSD, MIT, Zlib, CC0-1.0) |
| Streamlit | demonstrator | Apache-2.0 |
| requests | live URL scan, demo URL field | Apache-2.0 |
| imageio-ffmpeg | bundled ffmpeg for audio extraction | BSD-2-Clause; the bundled ffmpeg binary (checked in the linux-aarch64 wheel) is built with `--enable-gpl --enable-version3`, i.e. GPL-3.0. It is run as a separate program, not linked. Redistributing the container image redistributes that binary, so the GPL source offer applies (ffmpeg.org) |
| pytest | tests | MIT |
| python:3.12-slim-bookworm (container base) | runtime image | Python: PSF-2.0; Debian packages: their own free licences (Debian policy) |
| uv (developer tool, not shipped) | compiles `requirements.lock` | Apache-2.0 / MIT |
| GitHub Actions (CI) | tests on 3 systems, container smoke test | GitHub terms of service |
| rdap.org and the registries' RDAP servers | domain registration, IP network | public service; registry terms of use; rate limited |
| Google Public DNS (DNS over HTTPS) | does a domain resolve | Google Public DNS terms |
| Cert Spotter API (SSLMate) / crt.sh (Sectigo) | Certificate Transparency records | free tier without a key, rate limited / public service |
| Wayback Machine CDX API (Internet Archive) | first archived snapshot | Internet Archive terms of use |
| CERT Polska warning list (hole.cert.pl) | known dangerous domains | public list published by CERT Polska; checked locally, not redistributed |
| YuNet face detector (OpenCV Model Zoo, `face_detection_yunet_2023mar.onnx`) | find faces for the likeness report | MIT; downloaded on demand, not shipped |
| SFace face features (OpenCV Model Zoo, `face_recognition_sface_2021dec.onnx`) | compare faces across materials, no names | Apache-2.0; downloaded on demand, not shipped |
| faster-whisper (optional, not used yet) | speech to text | MIT |
| DeepFace (optional, not installed) | face matching against a small public-figure set | MIT code; model weights have their own terms, check before use |

Not used and to avoid: insightface pretrained models (non-commercial), spaCy `pl_core_news_sm` (GPL-3.0).
