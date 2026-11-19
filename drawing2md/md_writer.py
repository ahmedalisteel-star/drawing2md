"""Render the dicts produced by dxf_reader / pdf_reader as Markdown.

Renderers are generators of lines so huge drawings are written to disk
incrementally instead of being built as one giant string.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Iterator

from . import __version__

FOOTER = (f"*Generated offline by drawing2md {__version__} - no AI, no network. "
          "Coordinates rounded to 3 decimals.*")


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #
def num(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(v)


def p(point: Any) -> str:
    """(x, y) or (x, y, z) - z is dropped when it is 0."""
    if not point:
        return ""
    vals = list(point)
    if len(vals) >= 3 and vals[2] == 0:
        vals = vals[:2]
    return "(" + ", ".join(num(v) for v in vals) + ")"


def plist(points: Iterable[Any]) -> str:
    return " ".join(p(x) for x in points)


def cell(v: Any) -> str:
    s = num(v) if not isinstance(v, str) else v
    s = s.replace("\\", "\\\\").replace("|", "\\|")
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip().replace("\n", "<br>")
    return s


def table(headers: list[str], rows: Iterable[Iterable[Any]]) -> Iterator[str]:
    yield "| " + " | ".join(cell(h) for h in headers) + " |"
    yield "|" + "|".join("---" for _ in headers) + "|"
    for row in rows:
        yield "| " + " | ".join(cell(c) for c in row) + " |"
    yield ""


def heading(level: int, text: str) -> Iterator[str]:
    yield "#" * level + " " + text
    yield ""


def _bulge_vertices(verts: list) -> str:
    out = []
    for v in verts:
        bulge = v[-1]
        xyz = v[:-1]
        s = p(xyz)
        if bulge:
            s = s[:-1] + f" b={num(bulge)})"
        out.append(s)
    return " ".join(out)


def _hatch_paths(paths: list) -> str:
    parts = []
    for i, path in enumerate(paths, 1):
        if path.get("path") == "polyline":
            parts.append(f"P{i} polyline: " + _bulge_vertices(path.get("vertices", [])))
        elif path.get("path") == "edges":
            edges = []
            for e in path.get("edges", []):
                k = e.get("edge")
                if k == "line":
                    edges.append(f"line {p(e['start'])}-{p(e['end'])}")
                elif k == "arc":
                    edges.append(f"arc c={p(e['center'])} r={num(e['radius'])} "
                                 f"{num(e['start_angle'])}..{num(e['end_angle'])}")
                elif k == "ellipse":
                    edges.append(f"ellipse c={p(e['center'])} major={p(e['major_axis'])} "
                                 f"ratio={num(e['ratio'])}")
                elif k == "spline":
                    edges.append(f"spline deg={e['degree']} ctrl={plist(e['control_points'])}")
                else:
                    edges.append(str(k))
            parts.append(f"P{i} edges: " + "; ".join(edges))
        else:
            parts.append(f"P{i} {path.get('path')}")
    return " / ".join(parts)


# Geometry table layout per DXF entity type: (headers, row-builder)
GEOMETRY_COLUMNS: dict[str, tuple[list[str], Any]] = {
    "LINE": (["handle", "start", "end", "length", "color"],
             lambda e: [e["handle"], p(e["start"]), p(e["end"]), e["length"], e["color"]]),
    "CIRCLE": (["handle", "center", "radius", "color"],
               lambda e: [e["handle"], p(e["center"]), e["radius"], e["color"]]),
    "ARC": (["handle", "center", "radius", "start angle", "end angle", "start pt", "end pt", "color"],
            lambda e: [e["handle"], p(e["center"]), e["radius"], e["start_angle"], e["end_angle"],
                       p(e.get("start_point")), p(e.get("end_point")), e["color"]]),
    "LWPOLYLINE": (["handle", "closed", "vertices", "points (x, y, b=bulge)", "color"],
                   lambda e: [e["handle"], e["closed"], e["vertex_count"],
                              _bulge_vertices(e["vertices"]), e["color"]]),
    "POLYLINE": (["handle", "mode", "closed", "vertices", "points", "color"],
                 lambda e: [e["handle"], e.get("mode", ""), e.get("closed", ""), e.get("vertex_count", ""),
                            _bulge_vertices(e.get("vertices", [])), e["color"]]),
    "ELLIPSE": (["handle", "center", "major axis", "ratio", "start param", "end param", "color"],
                lambda e: [e["handle"], p(e["center"]), p(e["major_axis"]), e["ratio"],
                           e["start_param"], e["end_param"], e["color"]]),
    "SPLINE": (["handle", "degree", "closed", "control points", "fit points", "color"],
               lambda e: [e["handle"], e["degree"], e["closed"], plist(e["control_points"]),
                          plist(e["fit_points"]), e["color"]]),
    "POINT": (["handle", "location", "color"], lambda e: [e["handle"], p(e["location"]), e["color"]]),
    "HATCH": (["handle", "pattern", "solid", "boundary", "color"],
              lambda e: [e["handle"], e["pattern"], e["solid"], _hatch_paths(e["paths"]), e["color"]]),
    "SOLID": (["handle", "vertices", "color"], lambda e: [e["handle"], plist(e["vertices"]), e["color"]]),
    "VIEWPORT": (["handle", "id", "center", "width", "height", "view center", "view height", "scale"],
                 lambda e: [e["handle"], e["id"], p(e["center"]), e["width"], e["height"],
                            p(e["view_center"]), e["view_height"], e["scale"]]),
}
GEOMETRY_COLUMNS["MPOLYGON"] = GEOMETRY_COLUMNS["HATCH"]
GEOMETRY_COLUMNS["TRACE"] = GEOMETRY_COLUMNS["SOLID"]
GEOMETRY_COLUMNS["3DFACE"] = GEOMETRY_COLUMNS["SOLID"]


def _generic_details(e: dict) -> str:
    skip = {"type", "handle", "layer", "color"}
    parts = []
    for k, v in e.items():
        if k in skip:
            continue
        if isinstance(v, list) and v and isinstance(v[0], list):
            parts.append(f"{k}: {plist(v)}")
        elif isinstance(v, list) and len(v) in (2, 3) and all(isinstance(x, (int, float)) for x in v):
            parts.append(f"{k}: {p(v)}")
        elif isinstance(v, dict):
            parts.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            parts.append(f"{k}: {num(v)}")
    return "; ".join(parts)


def summarize_entity(e: dict) -> str:
    """One-line description of any record (used in block entity lists)."""
    t = e.get("type")
    if t in ("TEXT", "MTEXT", "MULTILEADER"):
        return f"\"{e.get('text', '')}\" at {p(e.get('insert'))} h={num(e.get('height'))}"
    if t == "INSERT":
        return f"block {e.get('block')} at {p(e.get('insert'))} rot={num(e.get('rotation'))}"
    if t in GEOMETRY_COLUMNS:
        headers, build = GEOMETRY_COLUMNS[t]
        vals = build(e)
        return "; ".join(f"{h}: {num(v)}"
                         for h, v in zip(headers, vals) if h not in ("handle", "color") and v not in ("", None))
    return _generic_details(e)


def _counts_line(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "none"


def _truncated_note(trunc: dict) -> Iterator[str]:
    if trunc:
        yield ("> **Note:** lists capped by --max-entities; not listed: "
               + ", ".join(f"{v} {k}" for k, v in trunc.items()) + ". Counts above are complete.")
        yield ""


# --------------------------------------------------------------------------- #
# DXF / DWG
# --------------------------------------------------------------------------- #
def _dxf_texts(layouts: list, blocks: list) -> list[tuple[str, dict]]:
    items = []
    for lay in layouts:
        for t in lay["texts"]:
            items.append((lay["name"], t))
    for b in blocks:
        for t in b["texts"]:
            items.append((f"block {b['name']}", t))
    return items


def iter_dxf_markdown(data: dict) -> Iterator[str]:
    info = data["info"]
    layouts, blocks, layers = data["layouts"], data["blocks"], data["layers"]
    all_inserts = [(lay["name"], i) for lay in layouts for i in lay["inserts"]] + \
                  [(f"block {b['name']}", i) for b in blocks for i in b["inserts"]]
    all_dims = [(lay["name"], d) for lay in layouts for d in lay["dimensions"]]
    texts = _dxf_texts(layouts, blocks)
    attr_rows = [(where, ins, a) for where, ins in all_inserts for a in ins.get("attribs", [])]
    user_blocks = [b for b in blocks if not b["dimension_block"]]

    yield from heading(1, f"{info['file']}")
    yield from heading(2, "Summary")
    ext = info.get("extents")
    yield f"- **Source:** {info['source_type']} file `{info['file']}` ({info['size_bytes']:,} bytes)"
    if info.get("converted_from"):
        yield f"- **Converted from:** `{info['converted_from']}` with ODA File Converter (local)"
    yield f"- **DXF version:** {info['dxf_version']} ({info['release']})"
    yield f"- **Units:** {info['units']} ($INSUNITS = {info['insunits']})"
    if ext:
        size = [round(ext["max"][i] - ext["min"][i], 3) for i in range(2)]
        yield (f"- **Extents ({ext['source']}):** min {p(ext['min'])} max {p(ext['max'])} "
               f"-> size {num(size[0])} x {num(size[1])}")
    yield f"- **Layers:** {len(layers)}"
    yield (f"- **Layouts:** {len(layouts)} (" + ", ".join(
        f"{l['name']}: {l['entity_count']} entities" for l in layouts) + ")")
    yield f"- **Entities (all layouts):** {info['entity_count']:,}"
    top = list(data["entity_type_totals"].items())[:10]
    yield "- **Top entity types:** " + (", ".join(f"{k} {v}" for k, v in top) or "none")
    yield (f"- **Block definitions:** {len(user_blocks)} "
           f"(+{len(blocks) - len(user_blocks)} dimension blocks) | **Inserts:** {len(all_inserts)} "
           f"| **Attributes:** {len(attr_rows)}")
    yield f"- **Texts:** {len(texts)} | **Dimensions:** {len(all_dims)}"
    if data["errors"]:
        yield f"- **Warnings:** {len(data['errors'])} (see end of file)"
    if not data["options"]["geometry"]:
        yield "- **Geometry tables:** skipped (--no-geometry)"
    if data["options"]["max_entities"]:
        yield f"- **List cap:** {data['options']['max_entities']} per list (--max-entities)"
    yield ""

    # File info -------------------------------------------------------------
    yield from heading(2, "File info")
    rows = [(k, v if not isinstance(v, (list, dict)) else
             (p(v) if isinstance(v, list) else json.dumps(v))) for k, v in info.items()
            if k not in ("extents",)]
    if ext:
        rows.append(("extents min", p(ext["min"])))
        rows.append(("extents max", p(ext["max"])))
    yield from table(["property", "value"], rows)

    # Layers -------------------------------------------------------------------
    yield from heading(2, "Layers")
    lay_counts: dict[str, int] = defaultdict(int)
    for lay in layouts:
        for name, counts in lay["layer_type_counts"].items():
            lay_counts[name] += sum(counts.values())
    yield from table(
        ["name", "color", "linetype", "lineweight", "on", "frozen", "locked", "plot", "entities"],
        [(l["name"], l["color"] if "true_color" not in l else f"{l['color']} {l['true_color']}",
          l["linetype"], l["lineweight"], l["on"], l["frozen"], l["locked"], l["plot"],
          lay_counts.get(l["name"], 0)) for l in layers])

    # Summary counts ------------------------------------------------------------
    yield from heading(2, "Summary counts")
    yield from table(["entity type", "count"], data["entity_type_totals"].items())
    for lay in layouts:
        yield from heading(3, f"{lay['name']} ({lay['kind']}) - entities per layer")
        if not lay["layer_type_counts"]:
            yield "_empty_"
            yield ""
            continue
        yield from table(["layer", "total", "by type"],
                         [(name, sum(c.values()), _counts_line(c))
                          for name, c in lay["layer_type_counts"].items()])

    # Text ------------------------------------------------------------------
    yield from heading(2, f"Text ({len(texts)})")
    if texts:
        yield from table(["where", "type", "layer", "text", "insert", "height", "rotation", "style"],
                         [(w, t["type"], t["layer"], t.get("text", ""), p(t.get("insert")),
                           t.get("height"), t.get("rotation"), t.get("style", "")) for w, t in texts])
    else:
        yield "_No TEXT/MTEXT found._"
        yield ""

    # Blocks & attributes ----------------------------------------------------
    yield from heading(2, "Blocks & Attributes")
    yield from heading(3, f"Block inserts ({len(all_inserts)})")
    if all_inserts:
        yield from table(["where", "handle", "block", "layer", "position", "scale (x, y, z)", "rotation",
                          "attributes"],
                         [(w, i["handle"], i["block"] + (f" ({i['effective_name']})" if i.get("effective_name") else ""),
                           i["layer"], p(i["insert"]), p(i["scale"]), i["rotation"],
                           "; ".join(f"{a['tag']}={a['value']}" for a in i.get("attribs", [])))
                          for w, i in all_inserts])
    else:
        yield "_No block inserts._"
        yield ""
    yield from heading(3, f"Attributes ({len(attr_rows)})")
    if attr_rows:
        yield from table(["where", "block", "insert handle", "tag", "value", "position", "layer"],
                         [(w, i.get("effective_name") or i["block"], i["handle"], a["tag"], a["value"],
                           p(a["insert"]), a["layer"]) for w, i, a in attr_rows])
    else:
        yield "_No attributes._"
        yield ""
    attdefs = [(b["name"], a) for b in blocks for a in b["attdefs"]]
    if attdefs:
        yield from heading(3, f"Attribute definitions - ATTDEF ({len(attdefs)})")
        yield from table(["block", "tag", "prompt", "default", "invisible", "constant"],
                         [(bn, a["tag"], a["prompt"], a["default"], a["invisible"], a["constant"])
                          for bn, a in attdefs])
    yield from heading(3, f"Block definitions ({len(user_blocks)})")
    if user_blocks:
        yield from table(["name", "base point", "entities", "types", "attdefs", "xref"],
                         [(b["name"], p(b["base_point"]), b["entity_count"], _counts_line(b["type_counts"]),
                           ", ".join(a["tag"] for a in b["attdefs"]),
                           b.get("xref_path", "") if b["xref"] else "") for b in user_blocks])
        for b in user_blocks:
            records = b["texts"] + b["inserts"] + b["dimensions"] + b["geometry"]
            if not records:
                continue
            yield from heading(4, f"Block `{b['name']}` entities")
            yield from table(["#", "type", "layer", "handle", "details"],
                             [(n, e["type"], e["layer"], e["handle"], summarize_entity(e))
                              for n, e in enumerate(records, 1)])
            yield from _truncated_note(b["truncated"])

    # Dimensions --------------------------------------------------------------
    yield from heading(2, f"Dimensions ({len(all_dims)})")
    if all_dims:
        yield ("Measurement is in drawing units (degrees for angular dimensions). Displayed text = measurement x DIMLFAC, rounded "
               "(DIMRND/DIMDEC), with R/Ø prefix and override text applied; "
               "\"(computed)\" means the dimension had no rendered block and the text was rebuilt.")
        yield ""
        yield from table(["where", "handle", "type", "layer", "measurement", "DIMLFAC", "displayed text",
                          "override", "dimstyle", "points"],
                         [(w, d["handle"], d["dimtype"], d["layer"],
                           d["measurement"] if not isinstance(d["measurement"], list) else p(d["measurement"]),
                           d.get("dimlfac", ""),
                           d.get("displayed_text", "") + (" (computed)" if d.get("displayed_text_source") == "computed"
                                                          and d.get("displayed_text") else ""),
                           d.get("override_text", ""), d.get("dimstyle", ""),
                           "; ".join(f"{k}={p(v)}" for k, v in d["points"].items()))
                          for w, d in all_dims])
    else:
        yield "_No dimensions._"
        yield ""

    # Geometry ------------------------------------------------------------------
    yield from heading(2, "Geometry")
    if not data["options"]["geometry"]:
        yield "_Skipped (--no-geometry)._"
        yield ""
    for lay in layouts if data["options"]["geometry"] else []:
        yield from heading(3, f"{lay['name']} ({lay['kind']})")
        extra = {k: lay[k] for k in ("paper_width", "paper_height", "page_setup_name", "paper_size")
                 if k in lay}
        if extra:
            yield "Layout settings: " + ", ".join(f"{k} = {num(v)}" for k, v in extra.items())
            yield ""
        if not lay["geometry"]:
            yield "_No geometry entities._"
            yield ""
        by_layer: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for e in lay["geometry"]:
            by_layer[e["layer"]][e["type"]].append(e)
        for layer_name in sorted(by_layer):
            yield from heading(4, f"Layer `{layer_name}`")
            for etype in sorted(by_layer[layer_name]):
                recs = by_layer[layer_name][etype]
                yield f"**{etype}** ({len(recs)})"
                yield ""
                if etype in GEOMETRY_COLUMNS:
                    headers, build = GEOMETRY_COLUMNS[etype]
                    yield from table(headers, (build(e) for e in recs))
                else:
                    yield from table(["handle", "details"], ((e["handle"], _generic_details(e)) for e in recs))
        yield from _truncated_note(lay["truncated"])

    yield from _errors(data["errors"])
    yield "---"
    yield FOOTER
    yield ""


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _md_cells_table(cells: list[list[str]]) -> Iterator[str]:
    if not cells:
        return
    width = max(len(r) for r in cells)
    norm = [r + [""] * (width - len(r)) for r in cells]
    header = [c or f"col{i + 1}" for i, c in enumerate(norm[0])]
    yield from table(header, norm[1:])


def iter_pdf_markdown(data: dict) -> Iterator[str]:
    info, pages, totals = data["info"], data["pages"], data["totals"]
    yield from heading(1, info["file"])
    yield from heading(2, "Summary")
    yield f"- **Source:** PDF file `{info['file']}` ({info['size_bytes']:,} bytes), {info.get('pdf_version', '')}"
    yield f"- **Pages:** {info['page_count']}"
    sizes = sorted({f"{num(pg['width_mm'])} x {num(pg['height_mm'])} mm" for pg in pages})
    yield "- **Page sizes:** " + ", ".join(sizes)
    meta = info.get("metadata", {})
    for key in ("title", "author", "subject", "creator", "producer", "creationDate"):
        if meta.get(key):
            yield f"- **{key}:** {meta[key]}"
    yield (f"- **Text lines:** {totals.get('text_lines', 0)} | **Tables:** {totals.get('tables', 0)} "
           f"| **Images:** {totals.get('images', 0)}")
    yield (f"- **Vector paths:** {totals.get('vector_paths', 0)} (lines {totals.get('line', 0)}, "
           f"rects {totals.get('rect', 0)}, quads {totals.get('quad', 0)}, curves {totals.get('curve', 0)})")
    if info.get("layers"):
        yield "- **PDF layers (OCG):** " + ", ".join(
            l["name"] + ("" if l["on"] else " (off)") for l in info["layers"])
    special = [f"p{pg['number']}: {pg['status']}" for pg in pages if pg["status"] != "text layer"]
    if special:
        yield "- **Pages without text layer:** " + "; ".join(special)
    if data["errors"]:
        yield f"- **Warnings:** {len(data['errors'])} (see end of file)"
    if not data["options"]["geometry"]:
        yield "- **Vector paths:** skipped (--no-geometry)"
    yield "- **Coordinates:** PDF points (1/72 in), origin top-left, y down"
    yield ""

    yield from heading(2, "File info")
    rows = [("pages", info["page_count"]), ("pdf version", info.get("pdf_version", "")),
            ("encrypted", info["encrypted"]), ("OCR available", info["ocr_available"])]
    rows += [(k, v) for k, v in meta.items()]
    yield from table(["property", "value"], rows)

    yield from heading(2, "Pages overview")
    yield from table(["page", "size (pt)", "size (mm)", "rotation", "text lines", "tables", "images",
                      "vector paths", "status"],
                     [(pg["number"], f"{num(pg['width'])} x {num(pg['height'])}",
                       f"{num(pg['width_mm'])} x {num(pg['height_mm'])}", pg["rotation"], len(pg["text"]),
                       len(pg["tables"]), len(pg["images"]), pg["path_stats"]["paths"], pg["status"])
                      for pg in pages])

    for pg in pages:
        yield from heading(2, f"Page {pg['number']}")
        yield (f"Size {num(pg['width'])} x {num(pg['height'])} pt ({num(pg['width_mm'])} x "
               f"{num(pg['height_mm'])} mm), rotation {pg['rotation']} deg, status: {pg['status']}")
        yield ""

        yield from heading(3, f"Text ({len(pg['text'])} lines)")
        if pg["text"]:
            yield from table(["block", "text", "bbox (x0, y0, x1, y1)", "font", "size"],
                             [(t["block"], t["text"], p(t["bbox"]), t["font"], t["size"]) for t in pg["text"]])
        else:
            yield "_No text._"
            yield ""

        yield from heading(3, f"Tables ({len(pg['tables'])})")
        if not pg["tables"]:
            yield "_No tables detected._"
            yield ""
        for t in pg["tables"]:
            yield f"**Table {t['index'] + 1}** - {t['rows']} rows x {t['cols']} cols, bbox {p(t['bbox'])}"
            yield ""
            yield from _md_cells_table(t["cells"])

        yield from heading(3, f"Images ({len(pg['images'])})")
        if pg["images"]:
            yield from table(["xref", "pixels (w x h)", "colorspace", "bpc", "position(s) on page", "file"],
                             [(im["xref"], f"{im['width']} x {im['height']}", im["colorspace"], im["bpc"],
                               " ".join(p(b) for b in im.get("positions", [])), im.get("file", ""))
                              for im in pg["images"]])
        else:
            yield "_No images._"
            yield ""

        stats = pg["path_stats"]
        yield from heading(3, f"Vector paths ({stats['paths']})")
        if stats["paths"]:
            yield "Items: " + _counts_line(stats["items"])
            yield ""
            if stats["stroke_colors"]:
                yield "Stroke colors: " + _counts_line(stats["stroke_colors"])
                yield ""
        if not data["options"]["geometry"]:
            yield "_Skipped (--no-geometry)._"
            yield ""
        elif pg["paths"]:
            yield from table(["path", "kind", "coordinates", "stroke", "fill", "width", "closed"],
                             [(v["path"], v["kind"],
                               plist(v["coords"]) if v["kind"] != "rect" else p(v["coords"][0]),
                               v["stroke"], v["fill"], v["width"], v["closed"]) for v in pg["paths"]])
            if pg["paths_truncated"]:
                yield (f"> **Note:** {pg['paths_truncated']} more path items not listed "
                       "(--max-entities). Counts above are complete.")
                yield ""
        else:
            yield "_No vector paths._"
            yield ""

    yield from _errors(data["errors"])
    yield "---"
    yield FOOTER
    yield ""


def _errors(errors: list) -> Iterator[str]:
    if errors:
        yield from heading(2, f"Warnings ({len(errors)})")
        for e in errors:
            yield f"- {cell(e)}"
        yield ""


def iter_markdown(data: dict) -> Iterator[str]:
    if data["kind"] == "pdf":
        return iter_pdf_markdown(data)
    return iter_dxf_markdown(data)


def render_markdown(data: dict) -> str:
    return "\n".join(iter_markdown(data))


def write_markdown(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for line in iter_markdown(data):
            fh.write(line)
            fh.write("\n")


def write_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, default=str)
