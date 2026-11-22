"""Likeness of people: is the same face used in two materials? (No names, no reference set needed.)

    python -m ads.preprocess.likeness --download            # the two OpenCV Zoo models (~39 MB) into .cache/models
    python -m ads.preprocess.likeness --matrix [--source ad|page|all]   # best face match between every pair of cases
    python -m ads.preprocess.likeness --gold                # how well "same face" separates gold campaigns

Faces are found with YuNet and compared with SFace, both from the OpenCV Model Zoo and run by OpenCV itself (no
TensorFlow). Sources per case: ad screenshots, sampled video frames and the images of saved landing pages. Two faces
are the same person when the cosine of their SFace features reaches SAME_PERSON (0.363, OpenCV's published threshold).

Measured on the samples (METHODOLOGY section 10): the same face appears in materials of unrelated campaigns (a public
figure's likeness is reused across schemes) and the three health videos show different people, so "same face" is
reported in this tool and in the documentation but is not part of the score. Names of people still come from page
text, captions and transcripts; the LLM never identifies anyone from a face (CLAUDE.md rule 5).

Privacy: face features are biometric data. They are computed locally, cached only in .cache/likeness (gitignored)
and never written to profiles, the repository or the panel; no face is sent anywhere.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
from itertools import combinations
from typing import Dict, List, Optional

import numpy as np

from ..paths import CACHE, CASES, DATA

MODELS_DIR = os.path.join(CACHE, "models")
FACES_DIR = os.path.join(CACHE, "likeness")
ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
MODELS = {  # file: (path in the zoo, sha256, licence)
    "face_detection_yunet_2023mar.onnx": ("face_detection_yunet/face_detection_yunet_2023mar.onnx",
                                          "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", "MIT"),
    "face_recognition_sface_2021dec.onnx": ("face_recognition_sface/face_recognition_sface_2021dec.onnx",
                                            "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
                                            "Apache-2.0"),
}
SAME_PERSON = 0.363   # SFace cosine threshold published with the model
MIN_FACE = 60         # pixels; smaller faces (comment avatars, crowds) are not compared
VIDEO_FRAMES = 24


def download() -> None:
    import requests
    os.makedirs(MODELS_DIR, exist_ok=True)
    for name, (path, sha, _) in MODELS.items():
        f = os.path.join(MODELS_DIR, name)
        if os.path.exists(f) and _sha(f) == sha:
            continue
        r = requests.get(ZOO + path, timeout=120)
        r.raise_for_status()
        open(f, "wb").write(r.content)
        if _sha(f) != sha:
            os.remove(f)
            raise RuntimeError(f"checksum mismatch for {name}")


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _models():
    import cv2
    paths = [os.path.join(MODELS_DIR, n) for n in MODELS]
    if not all(os.path.exists(p) for p in paths):
        raise RuntimeError("face models missing: run  python -m ads.preprocess.likeness --download")
    return cv2.FaceDetectorYN.create(paths[0], "", (320, 320), 0.85), cv2.FaceRecognizerSF.create(paths[1], "")


def faces_in(img, det, rec, min_side: int = MIN_FACE) -> List[np.ndarray]:
    """Unit-length SFace features of the faces of at least min_side pixels in one BGR image."""
    import cv2
    h, w = img.shape[:2]
    s = min(1.0, 1280 / max(h, w))
    im = cv2.resize(img, (int(w * s), int(h * s))) if s < 1 else img
    det.setInputSize((im.shape[1], im.shape[0]))
    _, found = det.detect(im)
    out = []
    for f in found if found is not None else []:
        if min(f[2], f[3]) >= min_side * s:
            v = rec.feature(rec.alignCrop(im, f)).flatten().astype(np.float32)
            out.append(v / (np.linalg.norm(v) or 1.0))
    return out


def case_faces(cid: str, refresh: bool = False) -> Dict[str, np.ndarray]:
    """{"ad": features from screenshots and video frames, "page": from saved page images}; cached per case."""
    import cv2
    from .video import sample_frames
    cache = os.path.join(FACES_DIR, f"{cid}.npz")
    manifest = os.path.join(CASES, cid, "manifest.json")
    if not refresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(manifest):
        z = np.load(cache)
        return {"ad": z["ad"], "page": z["page"]}
    det, rec = _models()
    m = json.load(open(manifest, encoding="utf-8"))
    feats: Dict[str, list] = {"ad": [], "page": []}
    for part in m.get("parts", []):
        for i in part.get("images", []):
            img = cv2.imread(os.path.join(DATA, i))
            if img is not None:
                feats["ad"] += faces_in(img, det, rec)
        if part.get("video") and os.path.exists(os.path.join(DATA, part["video"])):
            frames, _ = sample_frames(os.path.join(DATA, part["video"]), VIDEO_FRAMES, part.get("crop_top", 0.0),
                                      part.get("crop_bottom", 0.0), None)
            for fr in frames:
                feats["ad"] += faces_in(fr["frame"], det, rec)
        if part.get("html"):
            for f in glob.glob(os.path.splitext(os.path.join(DATA, part["html"]))[0] + "_files/*"):
                img = cv2.imread(f)
                if img is not None and min(img.shape[:2]) >= 100:
                    feats["page"] += faces_in(img, det, rec)
    out = {k: np.array(v, dtype=np.float32).reshape(-1, 128) for k, v in feats.items()}
    os.makedirs(FACES_DIR, exist_ok=True)
    np.savez(cache, **out)
    return out


def best_match(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    """Highest cosine between any face of a and any face of b; None when either has no face."""
    if not len(a) or not len(b):
        return None
    return float((a @ b.T).max())


def pick(f: Dict[str, np.ndarray], source: str) -> np.ndarray:
    return np.concatenate([f["ad"], f["page"]]) if source == "all" else f[source]


def gold_report(source: str) -> Dict[str, object]:
    """Same-face matches on gold same-campaign, same-scheme and unrelated pairs (counts at SAME_PERSON)."""
    from ..evaluation.gold import BROAD, STRICT, gold_pairs, load_gold
    gold = load_gold()
    ids = sorted(set(gold.get("case_ids") or []) & set(os.listdir(CASES)))
    faces = {c: pick(case_faces(c), source) for c in ids}
    strict, broad = gold_pairs(gold, STRICT), gold_pairs(gold, BROAD)
    rows = {"strict": [], "same scheme": [], "unrelated": []}
    for a, b in combinations(ids, 2):
        v = best_match(faces[a], faces[b])
        if v is None:
            continue
        key = "strict" if (a, b) in strict else "same scheme" if (a, b) in broad else "unrelated"
        rows[key].append(v)
    return {k: {"pairs": len(v), "same_face": sum(x >= SAME_PERSON for x in v)} for k, v in rows.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Same face across materials (local, no names)")
    ap.add_argument("--download", action="store_true", help="fetch the two OpenCV Zoo models (~39 MB)")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--gold", action="store_true")
    ap.add_argument("--source", choices=["ad", "page", "all"], default="all")
    ap.add_argument("--refresh", action="store_true", help="recompute cached face features")
    a = ap.parse_args()
    if a.download:
        download()
        print("models ready in", MODELS_DIR)
    ids = sorted(c for c in os.listdir(CASES) if os.path.exists(os.path.join(CASES, c, "manifest.json")))
    if a.matrix:
        faces = {c: pick(case_faces(c, a.refresh), a.source) for c in ids}
        print(f"faces per case ({a.source}):", {c: len(f) for c, f in faces.items()})
        print("     " + "".join(f"{i:>6}" for i in ids))
        for x in ids:
            cells = ["   -  " if x == y or best_match(faces[x], faces[y]) is None else f"{best_match(faces[x], faces[y]):6.2f}"
                     for y in ids]
            print(f"{x:>4} " + "".join(cells))
        print(f"same person at cosine >= {SAME_PERSON}")
    if a.gold:
        print(json.dumps(gold_report(a.source), indent=2))
    if not (a.download or a.matrix or a.gold):
        sys.exit("use --download, --matrix or --gold")


if __name__ == "__main__":
    main()
