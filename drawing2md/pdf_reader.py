"""Extract everything from a PDF with PyMuPDF (plus optional local Tesseract OCR).

Coordinates are PDF points (1/72 inch) in PyMuPDF's page space:
origin at the top-left corner, y grows downwards.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from collections import Counter
from typing import Any

try:
    import pymupdf  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz as pymupdf  # type: ignore

log = logging.getLogger("drawing2md")

# PyMuPDF prints an advert for an extra layout package on stdout; keep output clean.
if hasattr(pymupdf, "no_recommend_layout"):
    pymupdf.no_recommend_layout()

ROUND = 3
PT_TO_MM = 25.4 / 72.0
OCR_DPI = 300
MAX_ERRORS_KEPT = 200


def r(v: Any) -> float:
    v = round(float(v), ROUND)
    return 0.0 if v == 0 else v


def bbox(rect: Any) -> list[float]:
    return [r(c) for c in tuple(rect)[:4]]


def xy(p: Any) -> list[float]:
    return [r(p[0]), r(p[1])]


def hex_color(c: Any) -> str:
    if c is None:
        return ""
    try:
        vals = list(c)
    except TypeError:
        return str(c)
    if len(vals) == 1:  # gray
        vals = vals * 3
    if len(vals) == 4:  # CMYK -> RGB (simple)
        cy, m, y, k = vals
        vals = [(1 - cy) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    return "#" + "".join("%02x" % max(0, min(255, round(v * 255))) for v in vals[:3])


# --------------------------------------------------------------------------- #
# OCR (optional, local Tesseract only)
# --------------------------------------------------------------------------- #
def find_tesseract() -> str | None:
    exe = shutil.which("tesseract")
    if exe:
        return exe
    if sys.platform.startswith("win"):
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            cand = os.path.join(root, "Tesseract-OCR", "tesseract.exe")
            if os.path.isfile(cand):
                return cand
    return None


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return find_tesseract() is not None


def ocr_page(page: Any, lang: str = "eng") -> list[dict[str, Any]]:
    """OCR one page; returns text lines with bounding boxes in PDF points."""
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = find_tesseract() or "tesseract"
    pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
    mode = "RGB" if pix.n >= 3 else "L"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    scale = 72.0 / OCR_DPI
    lines: dict[tuple, dict[str, Any]] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x0, y0 = data["left"][i] * scale, data["top"][i] * scale
        x1, y1 = x0 + data["width"][i] * scale, y0 + data["height"][i] * scale
        ln = lines.setdefault(key, {"words": [], "bbox": [x0, y0, x1, y1], "conf": []})
        ln["words"].append(word)
        ln["conf"].append(conf)
        b = ln["bbox"]
        ln["bbox"] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]
    out = []
    for key in sorted(lines):
        ln = lines[key]
        out.append({"block": key[0], "text": " ".join(ln["words"]), "bbox": [r(v) for v in ln["bbox"]],
                    "font": "OCR", "size": r(ln["bbox"][3] - ln["bbox"][1]),
                    "confidence": r(sum(ln["conf"]) / len(ln["conf"]))})
    return out


# --------------------------------------------------------------------------- #
# per-page extraction
# --------------------------------------------------------------------------- #
def _text_lines(page: Any) -> list[dict[str, Any]]:
    out = []
    d = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)
    for bno, block in enumerate(d.get("blocks", [])):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            fonts = Counter()
            for s in spans:
                fonts[(s.get("font", ""), r(s.get("size", 0)))] += len(s.get("text", ""))
            (font, size), _ = fonts.most_common(1)[0]
            direction = line.get("dir", (1, 0))
            out.append({"block": bno, "text": text.strip(), "bbox": bbox(line["bbox"]),
                        "font": font, "size": size,
                        "color": hex_color(pymupdf.sRGB_to_pdf(spans[0].get("color", 0))) if spans else "",
                        "dir": [r(direction[0]), r(direction[1])]})
    return out


def _paths(page: Any, cap: int | None, stats: Counter) -> tuple[list, int]:
    """Return (rows, truncated) for vector drawing items on the page."""
    rows: list[dict[str, Any]] = []
    truncated = 0
    for pno, path in enumerate(page.get_drawings()):
        stroke = hex_color(path.get("color"))
        fill = hex_color(path.get("fill"))
        width = path.get("width")
        stats["paths"] += 1
        if stroke:
            stats[f"stroke {stroke}"] += 1
        for item in path.get("items", []):
            op = item[0]
            if op == "l":
                kind, coords = "line", [xy(item[1]), xy(item[2])]
            elif op == "re":
                kind, coords = "rect", [bbox(item[1])]
            elif op == "qu":
                q = item[1]
                kind, coords = "quad", [xy(q.ul), xy(q.ur), xy(q.lr), xy(q.ll)]
            elif op == "c":
                kind, coords = "curve", [xy(item[1]), xy(item[2]), xy(item[3]), xy(item[4])]
            else:
                kind, coords = op, []
            stats[kind] += 1
            if cap is not None and len(rows) >= cap:
                truncated += 1
                continue
            rows.append({"path": pno, "kind": kind, "coords": coords, "stroke": stroke,
                         "fill": fill, "width": r(width) if width is not None else None,
                         "closed": bool(path.get("closePath", False)),
                         "layer": path.get("layer") or ""})
    return rows, truncated


def _drop_empty(cells: list[list[str]]) -> list[list[str]]:
    """Remove rows and columns that are completely empty.

    Newer PyMuPDF releases (layout-based table finder) can add blank spacer
    columns between the real ones; this gives the same table on every version.
    """
    rows = [row for row in cells if any(c for c in row)]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    keep = [j for j in range(width) if any(row[j] for row in rows)]
    return [[row[j] for j in keep] for row in rows]


def _tables(page: Any) -> list[dict[str, Any]]:
    out = []
    found = page.find_tables()
    for tno, tab in enumerate(found.tables):
        rows = tab.extract()
        clean = _drop_empty([[("" if c is None else str(c).strip()) for c in row] for row in rows])
        if not clean:
            continue
        out.append({"index": tno, "bbox": bbox(tab.bbox), "rows": len(clean),
                    "cols": max((len(rw) for rw in clean), default=0), "cells": clean})
    return out


def _images(doc: Any, page: Any, pno: int, save_dir: str | None, saved: dict) -> list[dict[str, Any]]:
    out = []
    for img in page.get_images(full=True):
        xref = img[0]
        rec: dict[str, Any] = {"xref": xref, "width": img[2], "height": img[3],
                               "bpc": img[4], "colorspace": img[5], "name": img[7]}
        try:
            rects = page.get_image_rects(xref)
            rec["positions"] = [bbox(rc) for rc in rects]
        except Exception:
            rec["positions"] = []
        if save_dir is not None:
            if xref in saved:
                rec["file"] = saved[xref]
            else:
                try:
                    info = doc.extract_image(xref)
                    if info and info.get("image"):
                        os.makedirs(save_dir, exist_ok=True)
                        fname = f"page{pno + 1}_img{xref}.{info.get('ext', 'png')}"
                        with open(os.path.join(save_dir, fname), "wb") as fh:
                            fh.write(info["image"])
                        rel = os.path.basename(save_dir) + "/" + fname
                        saved[xref] = rel
                        rec["file"] = rel
                except Exception as exc:
                    log.warning("Page %d: could not save image xref %d: %s", pno + 1, xref, exc)
        out.append(rec)
    return out


def _image_coverage(images: list[dict[str, Any]], page_area: float) -> float:
    if page_area <= 0:
        return 0.0
    area = 0.0
    for im in images:
        for b in im.get("positions", []):
            area += max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return min(1.0, area / page_area)


def read_pdf(path: str, max_entities: int | None = None, geometry: bool = True,
             images_dir: str | None = None, ocr: bool = True, ocr_lang: str = "eng",
             tables: bool = True) -> dict[str, Any]:
    """Read a PDF and return a dict with all extracted data.

    images_dir: folder where embedded images are saved (None = list only).
    """
    log.info("Reading PDF %s", path)
    errors: list[str] = []
    doc = pymupdf.open(path)
    if doc.needs_pass and not doc.authenticate(""):
        raise RuntimeError("PDF is password protected")
    can_ocr = ocr and ocr_available()

    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    info: dict[str, Any] = {
        "file": os.path.basename(path),
        "size_bytes": os.path.getsize(path),
        "source_type": "PDF",
        "page_count": doc.page_count,
        "pdf_version": meta.pop("format", ""),
        "metadata": meta,
        "encrypted": bool(doc.is_encrypted),
        "ocr_available": can_ocr,
    }
    try:
        ocgs = doc.get_ocgs() or {}
        info["layers"] = [{"name": v.get("name", ""), "on": bool(v.get("on", True))}
                          for _, v in sorted(ocgs.items())]
    except Exception:
        info["layers"] = []

    pages = []
    saved: dict[int, str] = {}
    for pno in range(doc.page_count):
        try:
            page = doc[pno]
        except Exception as exc:
            msg = f"page {pno + 1} could not be loaded: {exc}"
            log.warning(msg)
            errors.append(msg)
            continue
        rect = page.rect
        pg: dict[str, Any] = {
            "number": pno + 1,
            "width": r(rect.width), "height": r(rect.height),
            "width_mm": r(rect.width * PT_TO_MM), "height_mm": r(rect.height * PT_TO_MM),
            "rotation": page.rotation,
            "mediabox": bbox(page.mediabox),
        }

        def step(name: str, func, default):
            try:
                return func()
            except Exception as exc:
                msg = f"page {pno + 1}: {name} failed: {type(exc).__name__}: {exc}"
                log.warning(msg)
                if len(errors) < MAX_ERRORS_KEPT:
                    errors.append(msg)
                return default

        pg["text"] = step("text", lambda: _text_lines(page), [])
        pg["images"] = step("images", lambda: _images(doc, page, pno, images_dir, saved), [])
        pg["tables"] = step("tables", lambda: _tables(page), []) if tables else []

        stats: Counter = Counter()
        if geometry:
            rows, trunc = step("vector paths", lambda: _paths(page, max_entities, stats), ([], 0))
            pg["paths"] = rows
            pg["paths_truncated"] = trunc
        else:
            pg["paths"] = []
            pg["paths_truncated"] = 0
        pg["path_stats"] = {
            "paths": stats.get("paths", 0),
            "items": {k: v for k, v in stats.items() if k in ("line", "rect", "quad", "curve")},
            "stroke_colors": {k.split(" ", 1)[1]: v for k, v in stats.most_common() if k.startswith("stroke ")},
        }

        pg["status"] = "text layer"
        if not pg["text"]:
            coverage = _image_coverage(pg["images"], rect.width * rect.height)
            has_content = bool(pg["images"]) or stats.get("paths", 0) > 0 or not geometry
            if coverage >= 0.5:
                label = "scanned"
            elif has_content:
                label = "no text layer"
            else:
                label = "blank"
            if label == "blank" and not pg["images"]:
                pg["status"] = "blank page"
            elif can_ocr:
                lines = step("OCR", lambda: ocr_page(page, ocr_lang), [])
                pg["text"] = lines
                pg["status"] = f"{label} - OCR text ({len(lines)} lines)"
            else:
                pg["status"] = f"{label} - OCR not available"
        pages.append(pg)

    doc.close()
    totals = Counter()
    for pg in pages:
        totals["text_lines"] += len(pg["text"])
        totals["tables"] += len(pg["tables"])
        totals["images"] += len(pg["images"])
        totals["vector_paths"] += pg["path_stats"]["paths"]
        for k, v in pg["path_stats"]["items"].items():
            totals[k] += v
    return {
        "kind": "pdf",
        "info": info,
        "pages": pages,
        "totals": dict(totals),
        "options": {"max_entities": max_entities, "geometry": geometry, "ocr": ocr,
                    "images_dir": os.path.basename(images_dir) if images_dir else None},
        "errors": errors,
    }
