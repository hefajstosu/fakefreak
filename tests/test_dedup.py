"""Tests for duplicate detection and the graded decision. Synthetic images and texts only."""
import random

import numpy as np
from PIL import Image

from ads import dedup
from ads.decision import decide


def make_image(path, seed, size=(360, 640)):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (12, 7, 3), dtype=np.uint8)          # coarse random layout, like blocks of an ad
    Image.fromarray(small).resize(size, Image.BICUBIC).save(path)
    return path


def test_resized_and_recompressed_copy_is_a_duplicate_but_other_image_is_not(tmp_path):
    a = make_image(str(tmp_path / "a.png"), 1)
    b = str(tmp_path / "b.jpg")
    Image.open(a).resize((250, 444)).save(b, quality=35)               # smaller and heavily compressed
    c = make_image(str(tmp_path / "c.png"), 2)
    assert dedup.hamming(dedup.dhash(a), dedup.dhash(b)) <= dedup.IMAGE_MAX_DISTANCE
    assert dedup.hamming(dedup.dhash(a), dedup.dhash(c)) > 12


def test_text_hash_ignores_case_punctuation_and_spacing():
    assert dedup.text_hash("Hello,  WORLD!  Fake   news.") == dedup.text_hash("hello world fake news")


def test_near_duplicate_text_detection():
    rnd = random.Random(0)
    words = [f"w{rnd.randint(0, 5000)}" for _ in range(600)]
    a = " ".join(words)
    b = " ".join(words[:200] + ["changed", "words", "here"] + words[203:])
    other = " ".join(f"z{rnd.randint(0, 5000)}" for _ in range(600))
    assert dedup.sketch_jaccard(dedup.sketch(a), dedup.sketch(b)) >= dedup.TEXT_NEAR_DUP
    assert dedup.sketch_jaccard(dedup.sketch(a), dedup.sketch(other)) < 0.2


def case(img, text, final_url=None):
    return {"parts": [{"role": "ad_creative", "images": [img], "text": None},
                      {"role": "bridge_page", "images": [], "text": text}],
            "technical_summary": {"redirect_chain": [final_url] if final_url else []}}


def test_find_duplicates_reports_each_kind_of_reason(tmp_path):
    img = make_image(str(tmp_path / "x.png"), 7)
    other_img = make_image(str(tmp_path / "y.png"), 8)
    long_text = "some long page text about a platform " * 20
    base = dedup.fingerprint(case(img, long_text, "https://a.test/p?utm_id=1"))
    same_img = dedup.fingerprint(case(img, "different words " * 80, "https://b.test/q"))
    same_text = dedup.fingerprint(case(other_img, long_text, "https://c.test/r"))
    same_url = dedup.fingerprint(case(other_img, "unrelated words " * 80, "https://a.test/p?utm_id=2"))
    unrelated = dedup.fingerprint(case(other_img, "unrelated words " * 80, "https://d.test/z"))
    got = {d["case"]: d["reasons"] for d in dedup.find_duplicates(base, {"img": same_img, "txt": same_text, "url": same_url, "none": unrelated})}
    assert any("image" in r for r in got["img"])
    assert any("page text" in r for r in got["txt"])
    assert got["url"] == ["same final URL"]
    assert "none" not in got


def R(score, strong=()):
    return {"score": score, "strong_links": list(strong), "contributions": {}, "missing": []}


def test_decision_statuses():
    n = lambda s, st=(): [("c1", R(s, st))]  # noqa: E731
    assert decide(n(0.9), [{"case": "c9", "reasons": ["near-identical image (2/64 bits differ)"]}])["status"] == "duplicate"
    assert decide(n(0.9), [{"case": "c9", "reasons": ["near-identical page text"]}])["status"] == "same_content"
    assert decide(n(0.6, ["shared tracker ID: x"]), [])["status"] == "confirmed"
    assert decide(n(0.85), [])["status"] == "confirmed"
    assert decide(n(0.6), [])["status"] == "likely"
    assert decide(n(0.4), [])["status"] == "suggested_family"
    assert decide(n(0.1), [])["status"] == "new_unconfirmed"
    assert decide([], [])["status"] == "new_unconfirmed"
    assert decide(n(0.4), [], tau=0.35)["status"] == "likely"        # the slider threshold moves the boundary


def test_must_link_evidence_confirms_whatever_the_score_and_every_result_names_its_rule():
    low = [("c1", R(0.2))]
    d = decide(low, [], hard=[("c7", R(0.15, ["shared tracker ID: x"]))])
    assert d["status"] == "confirmed" and d["rule"] == "hard_evidence" and d["hard_case"] == "c7"
    assert d["hard_links"] == ["shared tracker ID: x"]
    assert decide(low, [])["rule"] == "nothing"
    assert decide([("c1", R(0.85))], [])["rule"] == "score_confirm"
    assert decide([("c1", R(0.6, ["shared tracker ID: x"]))], [])["rule"] == "tau_and_evidence"
    assert decide([("c1", R(0.6, ["shared domain: d.test"]))], [])["rule"] == "tau_only"  # supporting evidence only


def test_family_evidence_suggests_the_family_and_names_the_case():
    d = decide([("c1", R(0.2))], [], family_links=[("c4", R(0.25, ["shared session/form endpoint: POST */a/"]))])
    assert d["status"] == "suggested_family" and d["rule"] == "family_evidence" and d["family_case"] == "c4"
