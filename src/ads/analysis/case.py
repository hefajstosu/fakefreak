"""Material -> case_input: what an analyst has about one article, as the extraction expects it."""
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..preprocess import page_fp
from ..preprocess.html_text import MAX_TEXT, html_to_text
from ..schema import empty_tech

FILE_KINDS = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
              ".html": "html", ".htm": "html", ".har": "har", ".txt": "text",
              ".mp4": "video", ".mov": "video", ".webm": "video", ".m4v": "video"}
MAX_CREATIVES = 6   # screenshots sent to the LLM as the ad creative; more cost tokens without new information


def classify_files(paths: Sequence[str]) -> Dict[str, List[str]]:
    """Files by kind (image, html, har, text, video, unsupported), from their extension."""
    out: Dict[str, List[str]] = {}
    for p in paths:
        out.setdefault(FILE_KINDS.get(os.path.splitext(p)[1].lower(), "unsupported"), []).append(p)
    return out


def _page(text: str, medium: str = "text") -> Dict[str, Any]:
    return {"role": "bridge_page", "medium": medium, "text": text, "images": []}


def _scan(url: str, tech: Dict[str, Any], fps: list, notes: List[str]) -> Tuple[str, Dict[str, Any]]:
    """Fetch the URL like a phone visitor; returns its text and technical summary (preprocess/url_scan.py)."""
    from ..preprocess.url_scan import scan_url
    scan = scan_url(url)
    if not scan["ok"]:
        notes.append(f"could not fetch the page: {scan['error']}")
        return "", tech
    fps.append(scan["technical_summary"].pop("page_fingerprints", {}))
    notes += scan["notes"]
    if scan["final_url"].rstrip("/") != url.rstrip("/"):
        notes.append(f"redirected to {scan['final_url']}")
    return scan["text"], scan["technical_summary"]


def _read_hars(hars: Sequence[str], tech: Dict[str, Any], fps: list, notes: List[str]) -> None:
    from ..preprocess import har
    for h in hars:
        try:
            har.process(h, tech)
            fps.append(page_fp.from_har(h))
        except (ValueError, KeyError, OSError) as e:
            notes.append(f"could not read the network log {os.path.basename(h)}: {str(e)[:80]}")


def _domain_facts(tech: Dict[str, Any], hars: Sequence[str], notes: List[str]) -> None:
    """Public registration, hosting and certificate facts of the domains found (preprocess/domain_meta.py)."""
    if not (tech["urls_and_domains"] or tech["redirect_chain"]):
        return
    try:
        from ..preprocess import domain_meta as dm
        captured = (dm.capture_date({"hars": list(hars)}, "") if hars else None) or dm.today()
        tech["domain_and_cert_metadata"] = dm.case_metadata(tech, captured=captured)
    except Exception as e:  # noqa: BLE001 - registries can fail; the analysis goes on without them
        notes.append(f"domain metadata unavailable: {str(e)[:80]}")


def _contact_sheets(videos: Sequence[str], work_dir: Optional[str], notes: List[str]) -> List[str]:
    from ..preprocess import video
    sheets = []
    for v in videos:
        try:
            samples, _ = video.sample_frames(v, video.SAMPLES, 0.0, 0.0, None)
            sheet = os.path.join(work_dir or os.path.dirname(v), os.path.splitext(os.path.basename(v))[0] + "_sheet.jpg")
            video.make_contact_sheet(video.pick_keyframes(samples), sheet)
            sheets.append(sheet)
        except Exception as e:  # noqa: BLE001 - an unreadable video is reported, the rest is analysed
            notes.append(f"could not read the video {os.path.basename(v)}: {str(e)[:80]}")
    return sheets


def build_case(url: str = "", text: str = "", images: Sequence[str] = (), html_files: Sequence[str] = (),
               hars: Sequence[str] = (), videos: Sequence[str] = (), text_files: Sequence[str] = (),
               work_dir: Optional[str] = None, domain_meta: bool = True) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """In-memory case_input from a URL (scanned), pasted text, screenshots, saved HTML pages, HAR logs, videos and
    text files. Returns (None, notes) when nothing usable is given.

    Screenshots (at most MAX_CREATIVES) and video contact sheets (written to `work_dir`) are the ad creative; HTML
    pages, text files and the scanned plus pasted text are bridge pages (the fake article); a HAR log alone also
    gives the text of its pages. HAR logs and the scan give the technical traces and, with the pages, the page
    fingerprints; with `domain_meta` the domains found get public registry facts."""
    notes: List[str] = []
    tech: Dict[str, Any] = empty_tech()
    fps: list = []
    page_text = text.strip()
    if url.strip():
        scanned, tech = _scan(url.strip(), tech, fps, notes)
        page_text = "\n".join(t for t in (scanned, page_text) if t)
    _read_hars(hars, tech, fps, notes)
    if domain_meta:
        _domain_facts(tech, hars, notes)

    creatives = list(images)
    if len(creatives) > MAX_CREATIVES:
        notes.append(f"{len(creatives)} images given: the first {MAX_CREATIVES} are analysed as the ad creative")
        creatives = creatives[:MAX_CREATIVES]
    creatives += _contact_sheets(videos, work_dir, notes)
    parts: List[Dict[str, Any]] = []
    if creatives:
        parts.append({"role": "ad_creative", "medium": "image", "text": None, "images": creatives})
    if html_files:
        parts += [_page(html_to_text(p), "html") for p in html_files]
        fps += [page_fp.from_saved_page(p) for p in html_files]
    for t in text_files:
        body = open(t, encoding="utf-8", errors="ignore").read().strip()
        if body:
            parts.append(_page(body[:MAX_TEXT]))
    if hars and not (html_files or text_files or url.strip()):  # a log alone: read its pages
        for h in hars:
            try:
                parts += [_page(t) for t in page_fp.har_page_texts(h)[:3]]
            except (ValueError, KeyError, OSError):
                pass
    if page_text:
        parts.append(_page(page_text))
    if not parts:
        if hars:
            notes.append("the network logs hold no readable page: add the article text, a screenshot or the saved page")
        return None, notes

    merged = page_fp.merge(*fps)
    if merged["structure"] or merged["images"]:
        tech["page_fingerprints"] = merged
    return {"schema_version": "1.0", "case_id": "new", "parts": parts, "technical_summary": tech,
            "resolved_identities": []}, notes
