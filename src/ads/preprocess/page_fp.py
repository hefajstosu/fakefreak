"""Page fingerprints: what a landing page is built from, independent of its words.

    structure_sketch(html)   MinHash of the page's tag paths and CSS class tokens: two pages made from one template
                             share most of them even when every sentence, name and number differs
    image_hashes(items)      content hashes of the large raster images on the page (photos, banners): an operator
                             reuses one image kit across domains, while unrelated pages almost never share a file
    from_saved_page(path)    both, for a page saved by a browser ("page.html" plus its "page_files" folder)
    from_har(path)           both, for the HTML documents and image bodies recorded in a HAR log

Both go to technical_summary.page_fingerprints = {"structure": [[int, ...] per page], "images": [hash, ...]}.
Measured on the sample pages before this was written: tag-path similarity 1.00 and 0.75 for the two gold template
pairs against at most 0.34 for unrelated pairs; identical image files only inside those two pairs.
"""
import base64
import hashlib
import io
import json
import os
import re
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple

PERM = 64            # MinHash size
SHINGLE = 4          # tags per path shingle
MIN_SIDE = 100       # images smaller than this (icons, pixels, avatars) are not evidence
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_CONTENT = {"script", "style", "noscript", "template", "svg"}
DIGITS = re.compile(r"\d+")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", "")


class _Tokens(HTMLParser):
    """Tag-path shingles and class tokens of one HTML document."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.tokens = set()
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag in SKIP_CONTENT:
                self.skip += 1
            return
        path = (self.stack + [tag])[-SHINGLE:]
        self.tokens.add("p:" + ">".join(path))
        for name, value in attrs:
            if name == "class" and value:
                self.tokens.update("c:" + DIGITS.sub("", c) for c in value.split() if DIGITS.sub("", c).strip("-_"))
        if tag in SKIP_CONTENT:
            self.skip = 1
        elif tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.skip:
            if tag in SKIP_CONTENT:
                self.skip -= 1
            return
        if tag in self.stack:  # tolerate unclosed tags: close everything above the matching one
            while self.stack and self.stack.pop() != tag:
                pass


def _h(seed: int, token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=6, salt=seed.to_bytes(16, "little"))
                          .digest(), "little")  # 48 bits: stable across processes and safe as a JSON number


def structure_tokens(html: str) -> set:
    p = _Tokens()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 - malformed markup keeps what was parsed
        pass
    return p.tokens


def structure_sketch(html: str) -> Optional[List[int]]:
    """MinHash (PERM values) of the structure tokens, or None for an empty page."""
    tokens = structure_tokens(html)
    if len(tokens) < 5:
        return None
    return [min(_h(i, t) for t in tokens) for i in range(PERM)]


def sketch_similarity(a: List[int], b: List[int]) -> float:
    """Estimated Jaccard similarity of two structure sketches."""
    return sum(x == y for x, y in zip(a, b)) / max(len(a), 1)


def _image_size(data: bytes) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:  # noqa: BLE001 - not a raster image
        return None


def image_hash(data: bytes) -> Optional[str]:
    """Content hash of a raster image of at least MIN_SIDE px on both sides; None for svg, icons and non-images."""
    size = _image_size(data)
    if not size or min(size) < MIN_SIDE:
        return None
    return hashlib.sha1(data).hexdigest()[:16]


def image_hashes(items: Iterable[bytes]) -> List[str]:
    return sorted({h for h in (image_hash(d) for d in items) if h})


def _files_dir(html_path: str) -> Optional[str]:
    base = os.path.splitext(html_path)[0]
    for cand in (base + "_files", base + ".files"):
        if os.path.isdir(cand):
            return cand
    return None


def from_saved_page(html_path: str) -> Dict[str, list]:
    """Fingerprints of a browser-saved page: its HTML and the images in its "<name>_files" folder."""
    html = open(html_path, encoding="utf-8", errors="ignore").read()
    sketch = structure_sketch(html)
    images: List[bytes] = []
    d = _files_dir(html_path)
    if d:
        for root, _, files in os.walk(d):
            for f in files:
                if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                    with open(os.path.join(root, f), "rb") as fh:
                        images.append(fh.read())
    return {"structure": [sketch] if sketch else [], "images": image_hashes(images)}


def from_har(path: str) -> Dict[str, list]:
    """Fingerprints of the HTML documents and image bodies recorded in a HAR log (bodies only, never headers)."""
    entries = json.load(open(path, encoding="utf-8"))["log"]["entries"]
    sketches, images = [], []
    for e in entries:
        content = e.get("response", {}).get("content", {}) or {}
        mime, text = (content.get("mimeType") or "").lower(), content.get("text")
        if not text:
            continue
        if "html" in mime and e.get("request", {}).get("method") == "GET":
            body = base64.b64decode(text).decode("utf-8", "ignore") if content.get("encoding") == "base64" else text
            s = structure_sketch(body)
            if s:
                sketches.append(s)
        elif mime.startswith("image/") and "svg" not in mime and content.get("encoding") == "base64":
            try:
                images.append(base64.b64decode(text))
            except ValueError:
                pass
    return {"structure": sketches, "images": image_hashes(images)}


def merge(*fps: Dict[str, list]) -> Dict[str, list]:
    """One case's fingerprints from several pages and logs: distinct sketches, distinct image hashes."""
    structure, images = [], set()
    for fp in fps:
        for s in fp.get("structure", []):
            if s not in structure:
                structure.append(s)
        images.update(fp.get("images", []))
    return {"structure": structure, "images": sorted(images)}


def from_manifest(manifest: Dict, data_dir: str) -> Dict[str, list]:
    """Fingerprints of one case from its manifest: every saved HTML page (with its files) and every HAR log."""
    fps = [from_saved_page(os.path.join(data_dir, part["html"])) for part in manifest.get("parts", [])
           if part.get("html") and os.path.exists(os.path.join(data_dir, part["html"]))]
    fps += [from_har(os.path.join(data_dir, h)) for h in manifest.get("hars", []) if os.path.exists(os.path.join(data_dir, h))]
    return merge(*fps)
