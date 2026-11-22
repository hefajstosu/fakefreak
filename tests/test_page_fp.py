"""Page fingerprints (preprocess/page_fp.py) on synthetic pages and images; no network, no sample data."""
import base64
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image  # noqa: E402

from ads.preprocess import page_fp as pf  # noqa: E402
from ads.similarity import score  # noqa: E402
from ads import clustering  # noqa: E402
from test_similarity import make  # noqa: E402

TEMPLATE = """<html><body><div class="hdr top-{n}"><nav class="menu"><a>{w1}</a><a>{w2}</a></nav></div>
<main class="article"><h1 class="title">{w1}</h1><p class="lead">{w2}</p><div class="comments"><div class="c">
<img src="a.jpg"><span class="who">{w1}</span><p>{w2}</p></div><div class="c"><span>{w2}</span></div></div>
<form class="reg"><input name="phone"><button class="btn-{n}">{w1}</button></form></main></body></html>"""
OTHER = """<html><body><table><tr><td><b>{w}</b></td></tr></table><ul class="list"><li>{w}</li><li>{w}</li></ul>
<footer class="foot"><small>{w}</small></footer><section class="x"><article><h2>{w}</h2></article></section></body></html>"""


def png(color, size=(200, 150)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_one_template_with_other_words_scores_high_and_another_layout_low():
    a = pf.structure_sketch(TEMPLATE.format(n=1, w1="Inwestuj", w2="Zysk"))
    b = pf.structure_sketch(TEMPLATE.format(n=77, w1="Lek", w2="Zdrowie"))
    c = pf.structure_sketch(OTHER.format(w="Kasyno"))
    assert pf.sketch_similarity(a, b) >= 0.9 and pf.sketch_similarity(a, c) <= 0.3


def test_sketch_is_stable_across_processes():
    code = ("import sys; sys.path.insert(0, 'src'); from ads.preprocess import page_fp as pf; "
            "print(pf.structure_sketch(open('tests/_tpl.html').read())[:5])")
    tpl = os.path.join(os.path.dirname(__file__), "_tpl.html")
    open(tpl, "w", encoding="utf-8").write(TEMPLATE.format(n=1, w1="a", w2="b"))
    try:
        root = os.path.join(os.path.dirname(__file__), "..")
        outs = {subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True).stdout
                for _ in range(2)}
        assert len(outs) == 1 and outs.pop().startswith("[")
    finally:
        os.remove(tpl)


def test_image_hashes_keep_large_rasters_only():
    big, icon = png("red"), png("blue", (32, 32))
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"></svg>'
    assert len(pf.image_hashes([big, big, icon, svg, b"not an image"])) == 1


def test_saved_page_and_har_give_the_same_kind_of_fingerprint(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(TEMPLATE.format(n=1, w1="x", w2="y"), encoding="utf-8")
    (tmp_path / "page_files").mkdir()
    (tmp_path / "page_files" / "photo.jpg").write_bytes(png("green"))
    saved = pf.from_saved_page(str(page))
    har = {"log": {"entries": [
        {"request": {"method": "GET", "url": "https://x.test/"},
         "response": {"content": {"mimeType": "text/html", "text": TEMPLATE.format(n=2, w1="p", w2="q")}}},
        {"request": {"method": "GET", "url": "https://x.test/photo.jpg"},
         "response": {"content": {"mimeType": "image/png", "encoding": "base64",
                                  "text": base64.b64encode(png("green")).decode()}}}]}}
    hf = tmp_path / "log.har"
    hf.write_text(json.dumps(har), encoding="utf-8")
    logged = pf.from_har(str(hf))
    assert saved["images"] == logged["images"] and len(saved["images"]) == 1
    assert pf.sketch_similarity(saved["structure"][0], logged["structure"][0]) >= 0.9
    assert pf.merge(saved, logged)["images"] == saved["images"]


def test_page_features_score_and_a_shared_kit_is_family_evidence():
    kit = {"structure": [pf.structure_sketch(TEMPLATE.format(n=1, w1="a", w2="b"))], "images": ["h1", "h2", "h3"]}
    a, b = make(), make(scam="fake_investment", product="Other", text="different words entirely here")
    for p in (a, b):
        p["technical_artifacts"]["page_fingerprints"] = kit
    r = score(a, b)
    assert "page_structure" in r["contributions"] and "page_assets" in r["contributions"]
    assert any(s.startswith("shared page images") for s in r["strong_links"])
    assert clustering.is_family_link(r) and not clustering.is_must_link(r)
    c = make()
    assert "page_structure" in score(a, c)["missing"]  # no page on one side: dropped, not scored 0


def test_page_fingerprints_validate_and_stay_out_of_the_llm_prompt():
    from jsonschema import Draft7Validator
    from ads.llm.extract import build_parts
    from ads.paths import SCHEMAS
    schema = json.load(open(os.path.join(SCHEMAS, "case_input.schema.json"), encoding="utf-8"))
    tech = {"urls_and_domains": [], "redirect_chain": [], "tracker_ids": [], "dom_and_form_clues": [],
            "domain_and_cert_metadata": []}
    part = {"role": "bridge_page", "medium": "text", "text": "Artykuł", "images": []}
    case = {"schema_version": "1.0", "case_id": "t", "parts": [part], "technical_summary": dict(tech),
            "resolved_identities": []}
    before = build_parts(case)
    case["technical_summary"]["page_fingerprints"] = {"structure": [[1, 2, 3]], "images": ["abc"]}
    assert not list(Draft7Validator(schema).iter_errors(case))
    assert build_parts(case) == before
