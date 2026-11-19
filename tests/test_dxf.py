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
    assert counts["DIMENSION"] == 5
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
    assert values == [250, 500, 500, 500, 1000]
    assert any(d["override_text"] == "TYP." for d in dims)
    assert any(d["dimtype"] == "radius" for d in dims)
    assert all("defpoint" in d["points"] for d in dims)


def test_radius_and_diameter_displayed_text(sample_dxf):
    dims = _model(read_dxf(sample_dxf))["dimensions"]
    radius = next(d for d in dims if d["dimtype"] == "radius")
    diameter = next(d for d in dims if d["dimtype"] == "diameter")
    assert radius["measurement"] == 250 and radius["dimlfac"] == 1
    assert radius["displayed_text"] == "R250"
    assert diameter["measurement"] == 500
    assert diameter["displayed_text"] == "Ø500"
    # the text rebuilt from the dimstyle matches what ezdxf drew into the block
    for d in dims:
        assert d["displayed_text_source"] == "block"
        assert d["computed_text"] == d["displayed_text"], d["handle"]


def _dim_doc():
    doc = ezdxf.new("R2018", setup=True)
    return doc, doc.modelspace()


@pytest.mark.parametrize("kind, add, override, expected", [
    ("radius, DIMLFAC 100", "radius", {"dimlfac": 100}, "R25000"),
    ("diameter, DIMLFAC 1", "diameter", {"dimlfac": 1}, "Ø500"),
    ("radius, DIMLFAC 0.001 (mm -> m), 3 decimals", "radius",
     {"dimlfac": 0.001, "dimdec": 3, "dimzin": 0}, "R0.250"),
    ("radius, leading zero suppressed", "radius",
     {"dimlfac": 0.001, "dimdec": 3, "dimzin": 4}, "R.250"),
    ("diameter, DIMPOST suffix", "diameter", {"dimlfac": 1, "dimpost": "<> mm"}, "Ø500 mm"),
    # not an exact tie: ezdxf's renderer rounds ties half-to-even, AutoCAD half-up
    ("radius, DIMRND 30", "radius", {"dimlfac": 1, "dimrnd": 30}, "R240"),
])
def test_dimension_text_follows_dimstyle(kind, add, override, expected):
    doc, msp = _dim_doc()
    if add == "radius":
        dim = msp.add_radius_dim(center=(0, 0), radius=250, angle=45, override=override)
    else:
        dim = msp.add_diameter_dim(center=(0, 0), radius=250, angle=45, override=override)
    dim.render()
    rec = dxf_reader.dimension_record(dim.dimension)
    assert rec["computed_text"] == expected, kind
    assert rec["displayed_text"] == expected, kind  # same as the rendered block
    assert rec["dimlfac"] == override["dimlfac"]


@pytest.mark.parametrize("override_text, expected", [
    ("", "1000"),
    ("<>", "1000"),
    ("<> TYP.", "1000 TYP."),
    ("2x <>", "2x 1000"),
    ("SEE DETAIL", "SEE DETAIL"),
    (" ", ""),
])
def test_override_text_placeholder(override_text, expected):
    doc, msp = _dim_doc()
    dim = msp.add_linear_dim(base=(0, -50), p1=(0, 0), p2=(1000, 0), text=override_text,
                             override={"dimlfac": 1})
    dim.render()
    rec = dxf_reader.dimension_record(dim.dimension)
    assert rec["computed_text"] == expected
    if expected:
        assert rec["displayed_text"] == expected


def test_displayed_text_computed_when_block_missing():
    doc, msp = _dim_doc()
    # not rendered -> the DIMENSION has no geometry block, as in some exported DXFs
    ov = msp.add_radius_dim(center=(0, 0), radius=12.3456, angle=0,
                            override={"dimlfac": 1, "dimdec": 2, "dimzin": 8})
    ov.commit()  # store the overrides (XDATA) without creating the geometry block
    assert ov.dimension.get_geometry_block() is None
    rec = dxf_reader.dimension_record(ov.dimension)
    assert rec["displayed_text_source"] == "computed"
    assert rec["displayed_text"] == "R12.35"


def test_format_dimension_text_unit():
    fmt = dxf_reader.format_dimension_text
    base = dict(dxf_reader.DIMSTYLE_DEFAULTS)
    assert fmt("radius", 250, "", {**base, "dimdec": 0}) == "R250"
    assert fmt("diameter", 12.5, "", {**base, "dimdec": 2, "dimzin": 8}) == "Ø12.5"
    assert fmt("linear/rotated", 1003.4, "", {**base, "dimrnd": 5, "dimdec": 2}) == "1005.00"
    assert fmt("linear/rotated", 0.5, "", {**base, "dimdec": 3, "dimzin": 4, "dimdsep": 44}) == ",500"
    assert fmt("angular (2-line)", 45.0, "", {**base, "dimadec": 1}) == "45.0°"
    assert fmt("radius", 250, "%%c<>", {**base, "dimdec": 0}) == "ØR250"
    assert fmt("radius", None, "", base) == ""
    assert fmt("radius", 2.5, "", {**base, "dimdec": 0}) == "R3"  # half away from zero
    assert fmt("radius", 250, "", {**base, "dimrnd": 100, "dimdec": 0}) == "R300"
    # MTEXT codes in override text: \X splits text above/below the dimension line
    assert fmt("linear/rotated", 900, "450 \\X(MIN)", base) == "450\n(MIN)"
    assert fmt("linear/rotated", 900, "45\\U+00B0", base) == "45°"


def test_angular_measurement_from_group_42_is_converted_to_degrees():
    doc, msp = _dim_doc()
    ov = msp.add_angular_dim_2l(base=(5, 5), line1=((0, 0), (10, 0)), line2=((0, 0), (10, 10)),
                                override={"dimadec": 0})
    ov.commit()
    dim = ov.dimension
    dim.dxf.actual_measurement = 0.7853981633974483  # AutoCAD stores radians here
    rec = dxf_reader.dimension_record(dim)
    assert rec["measurement"] == 45.0
    assert rec["measurement_unit"] == "degrees"
    assert rec["computed_text"] == "45°"


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
