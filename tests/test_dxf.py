import json

import ezdxf
import pytest

from drawing2md import dxf_reader
from drawing2md.dxf_reader import read_dxf
from drawing2md.md_writer import render_markdown


def _model(data):
    return next(l for l in data["layouts"] if l["kind"] == "model space")


def test_file_info_and_layers(sample_dxf):
    data = read_dxf(sample_dxf)
    info = data["info"]
    assert info["dxf_version"] == "AC1032"
    assert info["release"] == "R2018"
    assert info["units"] == "Millimeters"
    assert info["insunits"] == 4
    assert "extents" in info
    layers = {l["name"]: l for l in data["layers"]}
    assert layers["WALLS"]["color"] == 1
    assert layers["HIDDEN"]["on"] is False
    assert layers["FROZEN"]["frozen"] is True
    assert info["layer_count"] == len(layers)


def test_counts(sample_dxf):
    data = read_dxf(sample_dxf)
    model = _model(data)
    counts = model["type_counts"]
    for t in ("LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE", "POINT",
              "HATCH", "SOLID", "3DFACE", "TEXT", "MTEXT", "INSERT", "DIMENSION"):
        assert counts.get(t, 0) >= 1, t
    assert counts["DIMENSION"] == 4
    assert model["layer_type_counts"]["WALLS"]["LINE"] == 1


def test_geometry_values_rounded(sample_dxf):
    model = _model(read_dxf(sample_dxf))
    geo = {g["type"]: g for g in model["geometry"]}
    assert geo["LINE"]["end"] == [1000.123, 0.0, 0.0]
    assert geo["LINE"]["length"] == 1000.123
    assert geo["CIRCLE"]["radius"] == 250
    assert geo["ARC"]["start_angle"] == 0 and geo["ARC"]["end_angle"] == 90
    lw = geo["LWPOLYLINE"]
    assert lw["closed"] is True and lw["vertex_count"] == 4
    assert lw["vertices"][1] == [100.0, 0.0, 0.5]  # bulge kept
    assert geo["ELLIPSE"]["ratio"] == 0.5
    assert len(geo["SPLINE"]["fit_points"]) == 4
    assert geo["POINT"]["location"] == [7.0, 8.0, 0.0]
    paths = geo["HATCH"]["paths"]
    assert paths[0]["path"] == "polyline" and len(paths[0]["vertices"]) == 4
    assert {e["edge"] for e in paths[1]["edges"]} == {"line", "arc"}
    assert len(geo["3DFACE"]["vertices"]) == 4


def test_text_and_mtext_cleaned(sample_dxf):
    model = _model(read_dxf(sample_dxf))
    texts = {t["type"]: t for t in model["texts"]}
    assert texts["TEXT"]["text"] == "GROUND FLOOR PLAN"
    assert texts["TEXT"]["height"] == 50
    mtext = texts["MTEXT"]["text"]
    assert "Steel grade S355" in mtext and "All bolts M20 8.8" in mtext
    assert "\\f" not in mtext and "{" not in mtext and "\\P" not in mtext


def test_blocks_inserts_attributes(sample_dxf):
    data = read_dxf(sample_dxf)
    model = _model(data)
    inserts = {i["block"]: i for i in model["inserts"]}
    tb = inserts["TITLE_BLOCK"]
    assert {a["tag"]: a["value"] for a in tb["attribs"]} == {"DWG_NO": "ST-101", "REV": "B"}
    mark = inserts["MARK"]
    assert mark["scale"][:2] == [2.0, 2.0] and mark["rotation"] == 45
    assert mark["attribs"][0]["value"] == "C1"
    blocks = {b["name"]: b for b in data["blocks"]}
    assert [a["tag"] for a in blocks["TITLE_BLOCK"]["attdefs"]] == ["DWG_NO", "REV"]
    assert blocks["TITLE_BLOCK"]["texts"][0]["text"] == "COMPANY"


def test_dimensions(sample_dxf):
    dims = _model(read_dxf(sample_dxf))["dimensions"]
    values = sorted(d["measurement"] for d in dims)
    assert values == [250, 500, 500, 1000]
    assert any(d["override_text"] == "TYP." for d in dims)
    assert any(d["dimtype"] == "radius" for d in dims)
    assert all("defpoint" in d["points"] for d in dims)


def test_paper_space_layout(sample_dxf):
    data = read_dxf(sample_dxf)
    paper = [l for l in data["layouts"] if l["kind"] == "paper space"]
    assert paper and paper[0]["name"] == "Layout1"
    assert paper[0]["texts"][0]["text"] == "SHEET 1 OF 1"
    assert paper[0]["type_counts"].get("VIEWPORT", 0) >= 1


def test_max_entities_caps_lists_but_not_counts(sample_dxf):
    data = read_dxf(sample_dxf, max_entities=2)
    model = _model(data)
    assert len(model["geometry"]) == 2
    assert model["truncated"]["geometry"] > 0
    assert model["type_counts"]["LINE"] == 1  # counts complete


def test_no_geometry(sample_dxf):
    data = read_dxf(sample_dxf, geometry=False)
    model = _model(data)
    assert model["geometry"] == []
    assert model["texts"] and model["inserts"] and model["dimensions"]


def test_bad_entity_is_logged_and_skipped(sample_dxf, monkeypatch, caplog):
    real = dxf_reader.geometry_record

    def flaky(e):
        if e.dxftype() == "CIRCLE":
            raise ValueError("corrupt circle")
        return real(e)

    monkeypatch.setattr(dxf_reader, "geometry_record", flaky)
    data = read_dxf(sample_dxf)
    model = _model(data)
    types = {g["type"] for g in model["geometry"]}
    assert "CIRCLE" not in types and "LINE" in types
    assert any("corrupt circle" in e for e in data["errors"])
    assert "corrupt circle" in caplog.text


def test_damaged_dxf_uses_recover(tmp_path):
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (1, 1))
    path = tmp_path / "broken.dxf"
    doc.saveas(path)
    # Drop the EOF marker - normal reading fails, recover mode copes.
    raw = path.read_text(encoding="cp1252").rstrip()
    assert raw.endswith("EOF")
    path.write_text(raw[: -len("EOF")], encoding="cp1252")
    data = read_dxf(str(path))
    assert _model(data)["type_counts"]["LINE"] == 1


def test_markdown_render(sample_dxf):
    data = read_dxf(sample_dxf)
    md = render_markdown(data)
    for heading in ("## Summary", "## File info", "## Layers", "## Summary counts", "## Text",
                    "## Blocks & Attributes", "## Dimensions", "## Geometry", "#### Layer `WALLS`"):
        assert heading in md, heading
    assert md.index("## Summary") < md.index("## Layers")
    assert "| Model | TITLE_BLOCK | " in md and "ST-101" in md
    assert "(1000.123, 0)" in md
    assert "1000.12345" not in md
    json.dumps(data)  # fully serialisable
