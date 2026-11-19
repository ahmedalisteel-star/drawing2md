"""Sample drawings generated on the fly - no third-party/copyrighted files."""

from __future__ import annotations

import ezdxf
import pytest

try:
    import pymupdf
except ImportError:  # pragma: no cover
    import fitz as pymupdf


def make_sample_dxf(path) -> str:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4  # millimeters
    doc.layers.add("WALLS", color=1)
    doc.layers.add("TEXT", color=2)
    doc.layers.add("DIMS", color=3)
    doc.layers.add("HIDDEN", color=4).off()
    doc.layers.add("FROZEN", color=5).freeze()
    msp = doc.modelspace()

    msp.add_line((0, 0), (1000.12345, 0), dxfattribs={"layer": "WALLS"})
    msp.add_circle((500, 500), 250, dxfattribs={"layer": "WALLS"})
    msp.add_arc((0, 0), 100, 0, 90, dxfattribs={"layer": "WALLS"})
    msp.add_lwpolyline([(0, 0, 0), (100, 0, 0.5), (100, 100, 0), (0, 100, 0)], format="xyb",
                       close=True, dxfattribs={"layer": "WALLS"})
    msp.add_polyline3d([(0, 0, 0), (10, 10, 10), (20, 0, 5)], dxfattribs={"layer": "WALLS"})
    msp.add_ellipse((200, 200), major_axis=(50, 0), ratio=0.5, dxfattribs={"layer": "WALLS"})
    msp.add_spline([(0, 0), (10, 20), (30, 10), (40, 40)], dxfattribs={"layer": "WALLS"})
    msp.add_point((7, 8), dxfattribs={"layer": "HIDDEN"})
    hatch = msp.add_hatch(color=1, dxfattribs={"layer": "WALLS"})
    hatch.paths.add_polyline_path([(0, 0), (50, 0), (50, 50), (0, 50)], is_closed=True)
    edge = hatch.paths.add_edge_path()
    edge.add_line((100, 0), (150, 0))
    edge.add_arc((125, 0), 25, 0, 180)
    msp.add_solid([(0, 0), (10, 0), (0, 10), (10, 10)], dxfattribs={"layer": "WALLS"})
    msp.add_3dface([(0, 0, 0), (10, 0, 0), (10, 10, 5), (0, 10, 5)], dxfattribs={"layer": "WALLS"})

    msp.add_text("GROUND FLOOR PLAN", height=50, rotation=0,
                 dxfattribs={"layer": "TEXT"}).set_placement((10, 1200))
    msp.add_mtext("{\\fArial|b1|i0;Steel grade} S355\\PAll bolts M20 8.8",
                  dxfattribs={"layer": "TEXT", "char_height": 25, "insert": (10, 1100)})

    title = doc.blocks.new("TITLE_BLOCK", base_point=(0, 0))
    title.add_lwpolyline([(0, 0), (400, 0), (400, 100), (0, 100)], close=True)
    title.add_text("COMPANY", height=10).set_placement((5, 80))
    title.add_attdef("DWG_NO", (5, 50), dxfattribs={"height": 8, "prompt": "Drawing number"})
    title.add_attdef("REV", (5, 30), dxfattribs={"height": 8, "prompt": "Revision"})
    ins = msp.add_blockref("TITLE_BLOCK", (2000, 0), dxfattribs={"layer": "TEXT", "rotation": 0})
    ins.add_auto_attribs({"DWG_NO": "ST-101", "REV": "B"})

    mark = doc.blocks.new("MARK")
    mark.add_circle((0, 0), 5)
    mark.add_attdef("MARK", (0, 0), dxfattribs={"height": 3})
    m = msp.add_blockref("MARK", (300, 300), dxfattribs={"xscale": 2, "yscale": 2, "rotation": 45})
    m.add_auto_attribs({"MARK": "C1"})

    msp.add_linear_dim(base=(0, -100), p1=(0, 0), p2=(1000, 0),
                       dxfattribs={"layer": "DIMS"}).render()
    msp.add_aligned_dim(p1=(0, 0), p2=(300, 400), distance=50,
                        dxfattribs={"layer": "DIMS"}).render()
    msp.add_radius_dim(center=(500, 500), radius=250, angle=45,
                       dxfattribs={"layer": "DIMS"}).render()
    msp.add_linear_dim(base=(0, -200), p1=(0, 0), p2=(500, 0), text="TYP.",
                       dxfattribs={"layer": "DIMS"}).render()

    psp = doc.layout("Layout1")
    psp.add_text("SHEET 1 OF 1", height=5).set_placement((10, 10))
    psp.add_viewport(center=(150, 100), size=(200, 150), view_center_point=(500, 500), view_height=1500)

    doc.saveas(path)
    return str(path)


def _rgb_pixmap(w: int, h: int):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pix.clear_with(200)
    for x in range(w):
        pix.set_pixel(x, x * h // w, (255, 0, 0))
    return pix


def make_sample_pdf(path) -> str:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)  # A4 landscape
    page.insert_text((50, 60), "GENERAL ARRANGEMENT", fontsize=20, fontname="helv")
    page.insert_text((50, 90), "Beam B1 HEA 200", fontsize=10, fontname="helv")

    shape = page.new_shape()
    shape.draw_line((50, 120), (400, 120))
    shape.draw_rect(pymupdf.Rect(60, 140, 200, 220))
    shape.draw_bezier((250, 150), (300, 100), (350, 250), (400, 150))
    shape.finish(color=(1, 0, 0), width=1.5)
    shape.commit()

    # A ruled table (title-block style schedule)
    x0, y0, cw, rh = 450, 300, 120, 25
    rows = [["MARK", "SECTION", "QTY"], ["B1", "HEA200", "4"], ["C1", "HEB300", "6"]]
    tshape = page.new_shape()
    for i in range(len(rows) + 1):
        tshape.draw_line((x0, y0 + i * rh), (x0 + 3 * cw, y0 + i * rh))
    for j in range(4):
        tshape.draw_line((x0 + j * cw, y0), (x0 + j * cw, y0 + len(rows) * rh))
    tshape.finish(color=(0, 0, 0), width=1)
    tshape.commit()
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            page.insert_text((x0 + j * cw + 5, y0 + i * rh + 17), val, fontsize=10)

    page.insert_image(pymupdf.Rect(50, 300, 150, 400), pixmap=_rgb_pixmap(40, 40))

    # Page 2: a "scanned" page - an image of text, no text layer.
    tmp = pymupdf.open()
    tp = tmp.new_page(width=595, height=842)
    tp.insert_text((60, 120), "SCANNED NOTE 123", fontsize=40)
    scan = tp.get_pixmap(dpi=120)
    tmp.close()
    p2 = doc.new_page(width=595, height=842)
    p2.insert_image(p2.rect, pixmap=scan)

    doc.set_metadata({"title": "Sample drawing", "author": "drawing2md tests"})
    doc.save(path, deflate=True)
    doc.close()
    return str(path)


@pytest.fixture
def sample_dxf(tmp_path):
    return make_sample_dxf(tmp_path / "sample.dxf")


@pytest.fixture
def sample_pdf(tmp_path):
    return make_sample_pdf(tmp_path / "sample.pdf")
