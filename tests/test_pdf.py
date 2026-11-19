import json
import os

import pytest

from drawing2md import pdf_reader
from drawing2md.md_writer import render_markdown
from drawing2md.pdf_reader import read_pdf


def test_pages_and_metadata(sample_pdf):
    data = read_pdf(sample_pdf, ocr=False)
    assert data["info"]["page_count"] == 2
    assert data["info"]["metadata"]["title"] == "Sample drawing"
    p1 = data["pages"][0]
    assert (p1["width"], p1["height"]) == (842, 595)
    assert p1["rotation"] == 0


def test_text_with_bbox_font_size(sample_pdf):
    p1 = read_pdf(sample_pdf, ocr=False)["pages"][0]
    lines = {t["text"]: t for t in p1["text"]}
    title = lines["GENERAL ARRANGEMENT"]
    assert title["size"] == 20
    assert "Helvetica" in title["font"]
    x0, y0, x1, y1 = title["bbox"]
    assert x0 == pytest.approx(50, abs=1) and x1 > x0 and y1 > y0


def test_vector_paths(sample_pdf):
    p1 = read_pdf(sample_pdf, ocr=False)["pages"][0]
    kinds = {v["kind"] for v in p1["paths"]}
    assert {"line", "rect", "curve"} <= kinds
    red = [v for v in p1["paths"] if v["stroke"] == "#ff0000"]
    assert red and red[0]["width"] == 1.5
    line = next(v for v in p1["paths"] if v["kind"] == "line")
    assert line["coords"] == [[50.0, 120.0], [400.0, 120.0]]


def test_tables(sample_pdf):
    p1 = read_pdf(sample_pdf, ocr=False)["pages"][0]
    assert len(p1["tables"]) == 1
    cells = p1["tables"][0]["cells"]
    assert cells[0] == ["MARK", "SECTION", "QTY"]
    assert ["B1", "HEA200", "4"] in cells


def test_images_saved(sample_pdf, tmp_path):
    img_dir = tmp_path / "sample_images"
    data = read_pdf(sample_pdf, images_dir=str(img_dir), ocr=False)
    img = data["pages"][0]["images"][0]
    assert img["width"] == 40 and img["height"] == 40
    assert img["positions"][0] == [50.0, 300.0, 150.0, 400.0]
    assert (tmp_path / img["file"]).is_file()


def test_scanned_page_without_ocr(sample_pdf, monkeypatch):
    monkeypatch.setattr(pdf_reader, "ocr_available", lambda: False)
    p2 = read_pdf(sample_pdf)["pages"][1]
    assert p2["status"] == "scanned - OCR not available"
    assert p2["text"] == []


@pytest.mark.skipif(not pdf_reader.ocr_available(), reason="Tesseract not installed")
def test_scanned_page_with_ocr(sample_pdf):
    p2 = read_pdf(sample_pdf)["pages"][1]
    assert p2["status"].startswith("scanned - OCR text")
    text = " ".join(t["text"] for t in p2["text"])
    assert "SCANNED" in text and "123" in text


def test_max_entities_and_no_geometry(sample_pdf):
    capped = read_pdf(sample_pdf, max_entities=3, ocr=False)["pages"][0]
    assert len(capped["paths"]) == 3 and capped["paths_truncated"] > 0
    assert capped["path_stats"]["items"]["line"] >= 10  # counts complete
    nogeo = read_pdf(sample_pdf, geometry=False, ocr=False)["pages"][0]
    assert nogeo["paths"] == [] and nogeo["text"]


def test_markdown_render(sample_pdf):
    data = read_pdf(sample_pdf, ocr=False)
    md = render_markdown(data)
    for heading in ("## Summary", "## File info", "## Pages overview", "## Page 1", "## Page 2",
                    "### Text", "### Tables", "### Images", "### Vector paths"):
        assert heading in md, heading
    assert "| MARK | SECTION | QTY |" in md
    assert "| B1 | HEA200 | 4 |" in md
    json.dumps(data)


def test_empty_spacer_columns_removed():
    cells = [["MARK", "", "SECTION", "", "QTY"], ["", "", "", "", ""], ["B1", "", "HEA200", "", "4"]]
    assert pdf_reader._drop_empty(cells) == [["MARK", "SECTION", "QTY"], ["B1", "HEA200", "4"]]
    assert pdf_reader._drop_empty([["", ""], ["", ""]]) == []
