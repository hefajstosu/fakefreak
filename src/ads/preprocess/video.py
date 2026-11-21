"""Turn a video ad / screen recording into the inputs the extraction prompt expects:
a Polish transcript and a 2x2 contact sheet of 4 representative keyframes.

Usage:
  python -m ads.preprocess.video video.mp4 out_dir [--model medium] [--language pl]
        [--samples 48] [--crop-top 0.06] [--crop-bottom 0.0] [--roi x,y,w,h]
        [--no-transcribe]

Outputs in out_dir:
  contact_sheet.jpg   2x2 sheet (no text overlays, so OCR sees only the video)
  transcript.txt      plain transcript (empty file if none)
  meta.json           duration, chosen timestamps, transcript segments, notes

Dependencies: opencv-python-headless, numpy, pillow; faster-whisper for speech-to-text
(decodes the audio itself, no system ffmpeg needed).

Notes for screen recordings of a social feed:
  * --crop-top removes the OS status bar (clock/battery are excluded features).
  * --roi (fractions of the frame, e.g. 0,0.1,1,0.7) restricts selection to the
    area where the ad plays. Without it, frames are picked from the whole screen.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

# Phrases Whisper tends to hallucinate over silence/music.
HALLUCINATIONS = (
    "napisy stworzone przez społeczność amara.org",
    "dziękuję za uwagę",
    "dziękuję za obejrzenie",
    "subskrybuj",
    "napisy wykonane przez",
)


def crop_frame(frame, crop_top, crop_bottom, roi):
    h, w = frame.shape[:2]
    if roi:
        x, y, rw, rh = roi
        return frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
    return frame[int(crop_top * h):h - int(crop_bottom * h), :]


def ahash(gray):
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    return (small > small.mean()).flatten()


def frame_stats(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (320, max(1, int(320 * gray.shape[0] / gray.shape[1]))))
    return {
        "contrast": float(small.std()),                       # ~0 for blank frames
        "sharpness": float(cv2.Laplacian(small, cv2.CV_64F).var()),
        "hash": ahash(gray),
    }


def sample_frames(path, n_samples, crop_top, crop_bottom, roi):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    duration = total / fps if total > 0 else 0.0
    out = []
    for i in range(n_samples):
        idx = int(total * (0.02 + 0.96 * i / max(1, n_samples - 1)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        frame = crop_frame(frame, crop_top, crop_bottom, roi)
        s = frame_stats(frame)
        s.update(idx=idx, t=idx / fps, frame=frame)
        out.append(s)
    cap.release()
    return out, duration


def pick_keyframes(samples, n=4, min_contrast=12.0, min_hash_dist=5):
    """One frame per temporal quarter: the sharpest non-blank, non-duplicate frame."""
    if not samples:
        return []
    chosen = []
    bounds = np.linspace(0, len(samples), n + 1).astype(int)
    for q in range(n):
        seg = samples[bounds[q]:bounds[q + 1]]
        ranked = sorted((s for s in seg if s["contrast"] >= min_contrast),
                        key=lambda s: s["sharpness"], reverse=True) or \
            sorted(seg, key=lambda s: s["contrast"], reverse=True)
        pick = None
        for s in ranked:
            if all(int((s["hash"] != c["hash"]).sum()) >= min_hash_dist for c in chosen):
                pick = s
                break
        chosen.append(pick or (ranked[0] if ranked else seg[0]))
    return chosen


def make_contact_sheet(frames, out_path, tile_w=640, tile_h=720):
    tiles = []
    for f in frames:
        rgb = cv2.cvtColor(f["frame"], cv2.COLOR_BGR2RGB)
        im = Image.fromarray(rgb)
        scale = min(tile_w / im.width, tile_h / im.height)
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))))
        tile = Image.new("RGB", (tile_w, tile_h), "white")
        tile.paste(im, ((tile_w - im.width) // 2, (tile_h - im.height) // 2))
        tiles.append(tile)
    while len(tiles) < 4:
        tiles.append(Image.new("RGB", (tile_w, tile_h), "white"))
    sheet = Image.new("RGB", (tile_w * 2, tile_h * 2), "white")
    for i, t in enumerate(tiles[:4]):
        sheet.paste(t, ((i % 2) * tile_w, (i // 2) * tile_h))
    sheet.save(out_path, quality=90)


def transcribe(path, model_size, language):
    """Return (text, segments, note). Never raises: missing audio/libs become a note."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, [], "faster-whisper not installed; no transcript"
    try:
        try:
            import ctranslate2
            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            cuda = False
        model = WhisperModel(model_size, device="cuda" if cuda else "cpu",
                             compute_type="float16" if cuda else "int8")
        segs, _info = model.transcribe(path, language=language, vad_filter=True,
                                       beam_size=5, condition_on_previous_text=False)
        kept = []
        for s in segs:
            text = s.text.strip()
            if s.no_speech_prob > 0.6 or s.avg_logprob < -1.0:
                continue
            if any(h in text.lower() for h in HALLUCINATIONS):
                continue
            kept.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
        return " ".join(k["text"] for k in kept), kept, None if kept else "no speech detected"
    except Exception as e:  # no audio stream, decode error, model download failure
        return None, [], f"transcription failed: {type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--language", default="pl")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--crop-top", type=float, default=0.0)
    ap.add_argument("--crop-bottom", type=float, default=0.0)
    ap.add_argument("--roi", default=None, help="x,y,w,h as fractions of the frame")
    ap.add_argument("--no-transcribe", action="store_true")
    a = ap.parse_args()
    roi = tuple(float(v) for v in a.roi.split(",")) if a.roi else None
    os.makedirs(a.out_dir, exist_ok=True)

    samples, duration = sample_frames(a.video, a.samples, a.crop_top, a.crop_bottom, roi)
    chosen = pick_keyframes(samples)
    make_contact_sheet(chosen, os.path.join(a.out_dir, "contact_sheet.jpg"))

    notes = []
    text, segments = None, []
    if not a.no_transcribe:
        text, segments, note = transcribe(a.video, a.model, a.language)
        if note:
            notes.append(note)
    open(os.path.join(a.out_dir, "transcript.txt"), "w", encoding="utf-8").write(text or "")
    meta = {
        "source": os.path.basename(a.video),
        "duration_s": round(duration, 1),
        "keyframe_times_s": [round(c["t"], 1) for c in chosen],
        "transcript_segments": segments,
        "notes": notes,
    }
    json.dump(meta, open(os.path.join(a.out_dir, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: meta[k] for k in ("duration_s", "keyframe_times_s", "notes")}))


if __name__ == "__main__":
    sys.exit(main())
