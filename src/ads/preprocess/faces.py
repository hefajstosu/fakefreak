"""Local face-recognition module: resolves unnamed people in ad creatives against a
CURATED reference set of public figures, and produces the [RESOLVED_IDENTITIES]
block for the extraction prompt. The LLM itself never identifies faces.

Reference set layout (public figures only, from public sources):
  refs/
    categories.json            {"Monika Olejnik": "journalist", "Adam Glapiński": "public_official", ...}
    Monika Olejnik/1.jpg 2.jpg ...
    Adam Glapiński/1.jpg ...

Commands:
  python -m ads.preprocess.faces build-index refs index.npz [--model Facenet512] [--detector retinaface]
  python -m ads.preprocess.faces identify index.npz out.json img1.png img2.jpg ... [--threshold 0.30] [--margin 0.05]
  python -m ads.preprocess.faces pool refs/categories.json pool.json

`pool` writes {category: [names]} which doubles as `replacement_pools.featured_people`
for the alternatives prompt (same-category swaps).

Privacy / legal (biometric data, GDPR art. 9): keep the reference set to public figures,
never add private individuals, never persist embeddings of faces that did not match
(this module stores none), and run it only on collected ad material.

Matching logic (`match_faces`) is pure numpy; DeepFace is imported lazily, so the
logic can be tested without TensorFlow. Thresholds must be tuned on your own data:
ads often contain small picture-in-picture or circular portraits and AI-altered faces.
"""
import argparse
import json
import os
import sys

import numpy as np

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
# Cosine-distance defaults per model (DeepFace's published thresholds).
DEFAULT_THRESHOLD = {"Facenet512": 0.30, "Facenet": 0.40, "ArcFace": 0.68, "VGG-Face": 0.68}


def l2norm(x):
    x = np.asarray(x, dtype=np.float32)
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-9)


def match_faces(embeddings, ref_emb, ref_names, threshold, margin=0.05):
    """For each query embedding return the best person or None.

    ref_emb: (R, D) one row per reference photo; ref_names: person name per row.
    A person's distance is the minimum over their photos. A match requires
    distance <= threshold AND (second-best person is farther by >= margin), so
    look-alikes and ambiguous faces stay unresolved.
    """
    q = l2norm(embeddings)
    r = l2norm(ref_emb)
    dist = 1.0 - q @ r.T                                      # cosine distance (Q, R)
    people = sorted(set(ref_names))
    names = np.array(ref_names)
    results = []
    for row in dist:
        per_person = np.array([row[names == p].min() for p in people])
        order = np.argsort(per_person)
        best = per_person[order[0]]
        second = per_person[order[1]] if len(order) > 1 else np.inf
        if best <= threshold and (second - best) >= margin:
            results.append({"name": people[order[0]], "distance": float(best),
                            "margin": float(second - best) if np.isfinite(second) else None})
        else:
            results.append({"name": None, "distance": float(best),
                            "nearest": people[order[0]], "margin": float(second - best)
                            if np.isfinite(second) else None})
    return results


# ---------- DeepFace-dependent parts (lazy import) ----------

def _represent(path, model, detector):
    from deepface import DeepFace
    return DeepFace.represent(img_path=path, model_name=model, detector_backend=detector,
                              enforce_detection=False, align=True)


def build_index(refs_dir, out_path, model, detector):
    cats = json.load(open(os.path.join(refs_dir, "categories.json"), encoding="utf-8"))
    embs, names = [], []
    for person in sorted(os.listdir(refs_dir)):
        pdir = os.path.join(refs_dir, person)
        if not os.path.isdir(pdir):
            continue
        if person not in cats:
            print(f"skip {person}: missing from categories.json", file=sys.stderr)
            continue
        for f in sorted(os.listdir(pdir)):
            if not f.lower().endswith(IMG_EXT):
                continue
            faces = _represent(os.path.join(pdir, f), model, detector)
            if len(faces) != 1:  # reference photos must contain exactly one face
                print(f"skip {person}/{f}: {len(faces)} faces", file=sys.stderr)
                continue
            embs.append(faces[0]["embedding"])
            names.append(person)
    np.savez(out_path, emb=np.array(embs, dtype=np.float32), names=np.array(names),
             model=model, detector=detector, categories=json.dumps(cats, ensure_ascii=False))
    print(f"indexed {len(names)} photos of {len(set(names))} people")


def identify(index_path, images, threshold, margin):
    idx = np.load(index_path, allow_pickle=False)
    model, detector = str(idx["model"]), str(idx["detector"])
    cats = json.loads(str(idx["categories"]))
    thr = threshold if threshold is not None else DEFAULT_THRESHOLD.get(model, 0.40)
    out = []
    for path in images:
        faces = _represent(path, model, detector)
        faces = [f for f in faces if f.get("face_confidence", 1) > 0.5]
        res = match_faces([f["embedding"] for f in faces], idx["emb"], list(idx["names"]),
                          thr, margin) if faces else []
        for f, r in zip(faces, res):
            a = f["facial_area"]
            out.append({
                "name": r["name"],
                "category_or_role": cats.get(r["name"]) if r["name"] else None,
                "identity_basis": "resolved_by_face_module" if r["name"] else "none",
                "requires_external_face_recognition": r["name"] is None,
                "distance": round(r["distance"], 3),
                "nearest_candidate_unconfirmed": r.get("nearest"),
                "source_image": os.path.basename(path),
                "face_box": {k: int(a[k]) for k in ("x", "y", "w", "h")},
            })
    return {"resolved_identities": out, "model": model, "threshold": thr, "margin": margin}


def build_pool(categories_path):
    cats = json.load(open(categories_path, encoding="utf-8"))
    pool = {}
    for name, cat in cats.items():
        pool.setdefault(cat, []).append(name)
    return pool


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-index")
    b.add_argument("refs"); b.add_argument("out")
    b.add_argument("--model", default="Facenet512"); b.add_argument("--detector", default="retinaface")
    i = sub.add_parser("identify")
    i.add_argument("index"); i.add_argument("out"); i.add_argument("images", nargs="+")
    i.add_argument("--threshold", type=float, default=None)
    i.add_argument("--margin", type=float, default=0.05)
    p = sub.add_parser("pool")
    p.add_argument("categories"); p.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "build-index":
        build_index(a.refs, a.out, a.model, a.detector)
    elif a.cmd == "identify":
        json.dump(identify(a.index, a.images, a.threshold, a.margin),
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    else:
        json.dump(build_pool(a.categories), open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
