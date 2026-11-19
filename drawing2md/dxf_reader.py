"""Extract everything from a DXF file into a plain, JSON-serialisable dict.

Uses ezdxf only. Every entity is processed inside its own try/except so a
single broken entity is logged and skipped instead of stopping the run.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

import ezdxf
from ezdxf import recover
from ezdxf.lldxf.const import DXFError, DXFStructureError

log = logging.getLogger("drawing2md")

ROUND = 3
MAX_ERRORS_KEPT = 200

# Entity types that go into their own sections instead of "geometry".
TEXT_TYPES = {"TEXT", "MTEXT"}
DIMENSION_TYPES = {"DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION"}
INSERT_TYPES = {"INSERT"}

ACAD_RELEASE = {
    "AC1004": "R9", "AC1006": "R10", "AC1009": "R12", "AC1012": "R13",
    "AC1014": "R14", "AC1015": "R2000", "AC1018": "R2004", "AC1021": "R2007",
    "AC1024": "R2010", "AC1027": "R2013", "AC1032": "R2018",
}

DIMTYPE_NAMES = {
    0: "linear/rotated", 1: "aligned", 2: "angular (2-line)", 3: "diameter",
    4: "radius", 5: "angular (3-point)", 6: "ordinate",
}


# --------------------------------------------------------------------------- #
# small value helpers
# --------------------------------------------------------------------------- #
def r(value: Any) -> float:
    """Round a number to 3 decimals and normalise -0.0."""
    v = round(float(value), ROUND)
    return 0.0 if v == 0 else v


def pt(p: Any) -> list[float]:
    """Convert a Vec2/Vec3/tuple to a rounded [x, y, z] list."""
    vals = list(p)
    if len(vals) == 2:
        vals.append(0.0)
    return [r(v) for v in vals[:3]]


def pts(points: Iterable[Any]) -> list[list[float]]:
    return [pt(p) for p in points]


def plain(value: Any) -> Any:
    """Make an arbitrary DXF attribute value JSON-friendly."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return r(value)
    if isinstance(value, str):
        return value
    if hasattr(value, "__iter__"):
        try:
            items = list(value)
            if items and all(isinstance(i, (int, float)) for i in items):
                return [r(i) for i in items]
            return [plain(i) for i in items]
        except Exception:  # pragma: no cover - defensive
            pass
    return str(value)


def _get(entity: Any, name: str, default: Any = None) -> Any:
    try:
        return entity.dxf.get(name, default)
    except Exception:
        return default


def color_name(aci: Any) -> str:
    if aci is None:
        return ""
    aci = int(aci)
    if aci == 256:
        return "ByLayer"
    if aci == 0:
        return "ByBlock"
    return str(aci)


def _extrusion(entity: Any) -> list[float] | None:
    ext = _get(entity, "extrusion")
    if ext is None:
        return None
    e = pt(ext)
    return None if e == [0.0, 0.0, 1.0] else e


# --------------------------------------------------------------------------- #
# entity records
# --------------------------------------------------------------------------- #
def base_record(e: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "type": e.dxftype(),
        "handle": _get(e, "handle", ""),
        "layer": _get(e, "layer", "0"),
        "color": color_name(_get(e, "color", 256)),
    }
    lt = _get(e, "linetype")
    if lt and lt.upper() != "BYLAYER":
        rec["linetype"] = lt
    ext = _extrusion(e)
    if ext:
        rec["extrusion"] = ext
    return rec


def _hatch_paths(e: Any) -> list[dict[str, Any]]:
    out = []
    for path in e.paths:
        kind = type(path).__name__
        if hasattr(path, "vertices"):  # PolylinePath
            out.append({
                "path": "polyline",
                "closed": bool(getattr(path, "is_closed", True)),
                "vertices": [[r(v[0]), r(v[1]), r(v[2]) if len(v) > 2 else 0.0]
                             for v in path.vertices],
            })
        elif hasattr(path, "edges"):  # EdgePath
            edges = []
            for edge in path.edges:
                ek = type(edge).__name__
                if ek == "LineEdge":
                    edges.append({"edge": "line", "start": pt(edge.start), "end": pt(edge.end)})
                elif ek == "ArcEdge":
                    edges.append({"edge": "arc", "center": pt(edge.center),
                                  "radius": r(edge.radius),
                                  "start_angle": r(edge.start_angle),
                                  "end_angle": r(edge.end_angle), "ccw": bool(edge.ccw)})
                elif ek == "EllipseEdge":
                    edges.append({"edge": "ellipse", "center": pt(edge.center),
                                  "major_axis": pt(edge.major_axis), "ratio": r(edge.ratio),
                                  "start_angle": r(edge.start_angle),
                                  "end_angle": r(edge.end_angle), "ccw": bool(edge.ccw)})
                elif ek == "SplineEdge":
                    edges.append({"edge": "spline", "degree": int(edge.degree),
                                  "control_points": pts(edge.control_points),
                                  "fit_points": pts(edge.fit_points)})
                else:
                    edges.append({"edge": ek})
            out.append({"path": "edges", "edges": edges})
        else:
            out.append({"path": kind})
    return out


def geometry_record(e: Any) -> dict[str, Any]:
    """Return a dict describing the geometry of one entity."""
    t = e.dxftype()
    rec = base_record(e)

    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        rec.update(start=pt(s), end=pt(en), length=r((en - s).magnitude))
    elif t == "CIRCLE":
        rec.update(center=pt(e.dxf.center), radius=r(e.dxf.radius))
    elif t == "ARC":
        rec.update(center=pt(e.dxf.center), radius=r(e.dxf.radius),
                   start_angle=r(e.dxf.start_angle), end_angle=r(e.dxf.end_angle))
        try:
            rec.update(start_point=pt(e.start_point), end_point=pt(e.end_point))
        except Exception:
            pass
    elif t == "LWPOLYLINE":
        verts = [[r(x), r(y), r(b)] for x, y, b in e.get_points("xyb")]
        rec.update(closed=bool(e.closed), elevation=r(_get(e, "elevation", 0.0)),
                   const_width=r(_get(e, "const_width", 0.0)),
                   vertex_count=len(verts), vertices=verts)  # [x, y, bulge]
    elif t == "POLYLINE":
        mode = e.get_mode()
        rec["mode"] = mode
        if mode in ("AcDb2dPolyline", "AcDb3dPolyline"):
            verts = []
            for v in e.vertices:
                loc = pt(v.dxf.location)
                verts.append(loc + [r(v.dxf.get("bulge", 0.0))])  # [x, y, z, bulge]
            rec.update(closed=bool(e.is_closed), vertex_count=len(verts), vertices=verts)
        else:
            rec.update(vertex_count=len(e.vertices))
    elif t == "ELLIPSE":
        rec.update(center=pt(e.dxf.center), major_axis=pt(e.dxf.major_axis),
                   ratio=r(e.dxf.ratio), start_param=r(e.dxf.start_param),
                   end_param=r(e.dxf.end_param))
    elif t == "SPLINE":
        rec.update(degree=int(e.dxf.degree), closed=bool(e.closed),
                   control_points=pts(e.control_points), fit_points=pts(e.fit_points),
                   knots=[r(k) for k in e.knots], weights=[r(w) for w in e.weights])
    elif t == "POINT":
        rec.update(location=pt(e.dxf.location))
    elif t in ("HATCH", "MPOLYGON"):
        rec.update(pattern=_get(e, "pattern_name", ""), solid=bool(_get(e, "solid_fill", 0)),
                   associative=bool(_get(e, "associative", 0)), paths=_hatch_paths(e))
    elif t in ("SOLID", "TRACE", "3DFACE"):
        rec.update(vertices=[pt(e.dxf.get(f"vtx{i}")) for i in range(4)
                             if e.dxf.hasattr(f"vtx{i}")])
    elif t in ("XLINE", "RAY"):
        rec.update(start=pt(e.dxf.start), direction=pt(e.dxf.unit_vector))
    elif t == "LEADER":
        rec.update(vertices=pts(e.vertices), dimstyle=_get(e, "dimstyle", ""))
    elif t == "MLINE":
        rec.update(vertices=pts(e.get_locations()), style=_get(e, "style_name", ""))
    elif t in ("IMAGE", "WIPEOUT"):
        rec.update(insert=pt(e.dxf.insert), u_pixel=pt(e.dxf.u_pixel),
                   v_pixel=pt(e.dxf.v_pixel), image_size=pt(e.dxf.image_size))
        try:
            rec["boundary"] = pts(e.boundary_path_wcs())
        except Exception:
            pass
        if t == "IMAGE":
            try:
                rec["file"] = e.image_def.dxf.filename
            except Exception:
                pass
    elif t == "VIEWPORT":
        h = _get(e, "height", 0.0) or 0.0
        vh = _get(e, "view_height", 0.0) or 0.0
        rec.update(center=pt(e.dxf.center), width=r(_get(e, "width", 0.0)), height=r(h),
                   view_center=pt(_get(e, "view_center_point", (0, 0))), view_height=r(vh),
                   scale=f"1:{r(vh / h):g}" if h else "", id=_get(e, "id", 0))
    elif t == "MESH":
        rec.update(vertex_count=len(e.vertices), face_count=len(e.faces))
    elif t in ("3DSOLID", "REGION", "BODY", "SURFACE"):
        rec["note"] = "ACIS solid/region - geometry not decoded"
    elif t == "MULTILEADER":
        rec.update(text=_mleader_text(e))
    else:
        # Generic fallback: dump every DXF attribute ezdxf knows about.
        try:
            attribs = e.dxfattribs(drop={"handle", "owner", "layer", "color", "linetype"})
            rec["attribs"] = {k: plain(v) for k, v in attribs.items()}
        except Exception:
            pass
    return rec


def _mleader_text(e: Any) -> str:
    try:
        ctx = e.context
        if ctx.mtext is not None:
            from ezdxf.tools.text import plain_mtext
            return plain_mtext(ctx.mtext.default_content)
    except Exception:
        pass
    return ""


def text_record(e: Any) -> dict[str, Any]:
    t = e.dxftype()
    rec = base_record(e)
    if t == "TEXT":
        rec.update(text=e.plain_text(), insert=pt(e.dxf.insert),
                   height=r(_get(e, "height", 0.0)), rotation=r(_get(e, "rotation", 0.0)),
                   style=_get(e, "style", "Standard"))
    elif t == "MTEXT":
        try:
            rot = e.get_rotation()
        except Exception:
            rot = _get(e, "rotation", 0.0)
        rec.update(text=e.plain_text(split=False), insert=pt(e.dxf.insert),
                   height=r(_get(e, "char_height", 0.0)), rotation=r(rot or 0.0),
                   width=r(_get(e, "width", 0.0)), style=_get(e, "style", "Standard"))
    elif t == "MULTILEADER":
        rec.update(text=_mleader_text(e), insert=[0.0, 0.0, 0.0], height=0.0, rotation=0.0)
        try:
            rec["insert"] = pt(e.context.mtext.insert)
            rec["height"] = r(e.context.char_height)
        except Exception:
            pass
    return rec


def _attrib_text(a: Any) -> str:
    try:
        if a.has_embedded_mtext_entity:
            return a.virtual_mtext_entity().plain_text(split=False)
    except Exception:
        pass
    try:
        return a.plain_text()
    except Exception:
        return _get(a, "text", "")


def _effective_block_name(doc: Any, name: str) -> str:
    """Resolve anonymous dynamic-block names (*U12) to their real block name."""
    if not name.startswith("*"):
        return name
    try:
        br = doc.blocks.get(name).block_record
        if br.has_xdata("AcDbBlockRepBTag"):
            for code, value in br.get_xdata("AcDbBlockRepBTag"):
                if code == 1005:
                    owner = doc.entitydb.get(value)
                    if owner is not None:
                        return owner.dxf.name
    except Exception:
        pass
    return name


def insert_record(e: Any, doc: Any) -> dict[str, Any]:
    rec = base_record(e)
    name = e.dxf.name
    rec.update(block=name, insert=pt(e.dxf.insert),
               scale=[r(_get(e, "xscale", 1.0)), r(_get(e, "yscale", 1.0)), r(_get(e, "zscale", 1.0))],
               rotation=r(_get(e, "rotation", 0.0)))
    eff = _effective_block_name(doc, name)
    if eff != name:
        rec["effective_name"] = eff
    cols, rows = _get(e, "column_count", 1), _get(e, "row_count", 1)
    if (cols or 1) > 1 or (rows or 1) > 1:
        rec.update(columns=cols, rows=rows, column_spacing=r(_get(e, "column_spacing", 0.0)),
                   row_spacing=r(_get(e, "row_spacing", 0.0)))
    attribs = []
    for a in e.attribs:
        try:
            attribs.append({"tag": a.dxf.tag, "value": _attrib_text(a),
                            "insert": pt(a.dxf.insert), "height": r(_get(a, "height", 0.0)),
                            "layer": _get(a, "layer", "0")})
        except Exception as exc:  # keep going
            log.warning("Bad ATTRIB in INSERT %s: %s", rec["handle"], exc)
    rec["attribs"] = attribs
    return rec


def dimension_record(e: Any) -> dict[str, Any]:
    rec = base_record(e)
    try:
        dimtype = int(e.dimtype)
    except Exception:
        dimtype = int(_get(e, "dimtype", 0)) & 7
    if e.dxftype() == "ARC_DIMENSION":
        kind = "arc length"
    elif e.dxftype() == "LARGE_RADIAL_DIMENSION":
        kind = "large radial (jogged)"
    else:
        kind = DIMTYPE_NAMES.get(dimtype, str(dimtype))
    angular = kind.startswith("angular")
    measurement: Any = _get(e, "actual_measurement")
    if measurement is not None and angular:
        measurement = math.degrees(measurement)  # group 42 stores angles in radians
    if measurement is None:
        try:
            measurement = e.get_measurement()  # ezdxf returns degrees for angular dims
        except Exception:
            measurement = None
    if measurement is not None:
        measurement = plain(measurement)
    override = _get(e, "text", "") or ""
    style = _effective_dimstyle(e)
    computed = format_dimension_text(kind, measurement, override, style)
    drawn = _dimension_displayed_text(e)
    rec.update(dimtype=kind, measurement=measurement,
               measurement_unit="degrees" if angular else "drawing units", override_text=override,
               # what the drawing shows: the rendered block text when present,
               # otherwise the text rebuilt from the dimstyle rules
               displayed_text=drawn if drawn else computed,
               displayed_text_source="block" if drawn else "computed",
               computed_text=computed,
               dimstyle=_get(e, "dimstyle", ""),
               dimlfac=r(style["dimlfac"]), dimrnd=r(style["dimrnd"]), dimdec=style["dimdec"])
    points = {}
    for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
        v = _get(e, name)
        if v is not None:
            points[name] = pt(v)
    rec["points"] = points
    angle = _get(e, "angle")
    if angle:
        rec["angle"] = r(angle)
    return rec


SPECIAL_CODES = {"%%c": "Ø", "%%C": "Ø", "%%d": "°", "%%D": "°",
                 "%%p": "±", "%%P": "±"}

# AutoCAD defaults, used when neither the dimension nor its dimstyle sets a value
DIMSTYLE_DEFAULTS = {"dimlfac": 1.0, "dimrnd": 0.0, "dimdec": 4, "dimzin": 0, "dimdsep": 46,
                     "dimpost": "", "dimadec": 0, "dimazin": 0, "dimapost": ""}


_UNICODE_ESCAPE = re.compile(r"\\U\+([0-9A-Fa-f]{4})")
_LINE_BREAK_SPACES = re.compile(r"[ \t]*\n[ \t]*")


def _special_codes(text: str) -> str:
    """Decode %%c/%%d/%%p and backslash-U+XXXX escapes left by plain-text conversion."""
    for code, char in SPECIAL_CODES.items():
        text = text.replace(code, char)
    return _UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)


def _mtext_plain(raw: str) -> str:
    """MTEXT -> plain text; the backslash-X code (text above/below the dimension line)
    becomes a line break."""
    raw = raw.replace("\\X", "\\P")
    try:
        from ezdxf.tools.text import plain_mtext
        text = plain_mtext(raw, split=False)
    except Exception:
        text = raw
    return _LINE_BREAK_SPACES.sub("\n", text)


def _effective_dimstyle(e: Any) -> dict[str, Any]:
    """Dimstyle values for one DIMENSION, including per-entity overrides (XDATA)."""
    values = dict(DIMSTYLE_DEFAULTS)
    try:
        ov = e.override()  # DimStyleOverride: entity override -> dimstyle
        getter = ov.get
    except Exception:
        style = None
        try:
            style = e.doc.dimstyles.get(_get(e, "dimstyle", "Standard"))
        except Exception:
            pass
        getter = (lambda k, d=None: style.dxf.get(k, d)) if style is not None else (lambda k, d=None: d)
    for key, default in DIMSTYLE_DEFAULTS.items():
        try:
            v = getter(key, None)
        except Exception:
            v = None
        if v is not None:
            values[key] = v
    return values


def _half_up(value: float, quantum: str) -> Decimal:
    """Round half away from zero like AutoCAD (Python's round() is half-to-even)."""
    return Decimal(repr(float(value))).quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


def _round_to(value: float, step: float) -> float:
    """DIMRND: round to the nearest multiple of step."""
    if step and step > 0:
        return float(_half_up(value / step, "1")) * step
    return value


def _format_number(value: float, decimals: int, dimzin: int, dsep: int) -> str:
    decimals = max(0, int(decimals))
    s = format(_half_up(value, "1" if decimals == 0 else "0." + "0" * decimals), "f")
    if "." in s:
        if dimzin & 8:  # suppress trailing zeros
            s = s.rstrip("0").rstrip(".")
        if dimzin & 4:  # suppress leading zero: 0.5 -> .5
            if s.startswith("0."):
                s = s[1:]
            elif s.startswith("-0."):
                s = "-" + s[2:]
    if s in ("-0", "-", ""):
        s = "0"
    sep = chr(int(dsep)) if dsep else "."
    return s.replace(".", sep) if sep != "." else s


def _apply_post(core: str, post: str, prefix: str) -> str:
    """Apply DIMPOST/DIMAPOST. 'Prefix<>Suffix' or a plain suffix."""
    post = post or ""
    if "<>" in post:
        before, after = post.split("<>", 1)
        # A DIMPOST prefix replaces the default R / diameter prefix (AutoCAD behaviour).
        return f"{before or prefix}{core}{after}"
    return f"{prefix}{core}{post}"


def format_dimension_text(kind: str, measurement: Any, override: str,
                          style: dict[str, Any]) -> str:
    """Rebuild the dimension text the way AutoCAD composes it.

    measurement is in drawing units (degrees for angular dimensions).
    Linear values are multiplied by DIMLFAC, rounded to DIMRND, formatted with
    DIMDEC/DIMZIN/DIMDSEP, prefixed with R or the diameter sign, and DIMPOST is
    applied. The override text then replaces it: "" or "<>" -> measured text,
    "<>" inside text -> substituted, a single space -> text suppressed.
    """
    measured = ""
    if isinstance(measurement, (int, float)):
        if kind.startswith("angular"):
            dec = style.get("dimadec", 0)
            if dec is None or int(dec) < 0:
                dec = style.get("dimdec", 0)
            azin = int(style.get("dimazin", 0) or 0)  # 1 = leading, 2 = trailing zeros
            zin = (4 if azin & 1 else 0) | (8 if azin & 2 else 0)
            core = _format_number(float(measurement), dec, zin, style.get("dimdsep", 46)) + "°"
            measured = _apply_post(core, style.get("dimapost", ""), "")
        else:
            lfac = abs(float(style.get("dimlfac", 1.0) or 1.0))
            value = _round_to(float(measurement) * lfac, float(style.get("dimrnd", 0.0) or 0.0))
            core = _format_number(value, style.get("dimdec", 4), int(style.get("dimzin", 0) or 0),
                                  style.get("dimdsep", 46))
            prefix = {"radius": "R", "diameter": "Ø", "large radial (jogged)": "R"}.get(kind, "")
            measured = _apply_post(core, style.get("dimpost", ""), prefix)

    if override == " ":  # AutoCAD: single space suppresses the text
        return ""
    if override in ("", "<>"):
        text = measured
    elif "<>" in override:
        text = override.replace("<>", measured)
    else:
        text = override
    return _special_codes(_mtext_plain(text)).strip()


def _dimension_displayed_text(e: Any) -> str:
    """Text actually drawn by the dimension (taken from its geometry block)."""
    try:
        block = e.get_geometry_block()
        if block is None:
            return ""
        parts = []
        for sub in block:
            if sub.dxftype() == "MTEXT":
                parts.append(_mtext_plain(sub.text))
            elif sub.dxftype() == "TEXT":
                parts.append(sub.plain_text())
        return _special_codes("\n".join(p.strip() for p in parts if p.strip()))
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# document level
# --------------------------------------------------------------------------- #
def _load(path: str):
    """Read a DXF; fall back to ezdxf's recover mode for damaged files."""
    try:
        return ezdxf.readfile(path), []
    except (DXFStructureError, DXFError, UnicodeDecodeError, ValueError) as exc:
        log.warning("Normal DXF read failed (%s) - trying recover mode", exc)
        doc, auditor = recover.readfile(path)
        msgs = [f"recover: {err.message}" for err in auditor.errors[:MAX_ERRORS_KEPT]]
        return doc, msgs


def _file_info(doc: Any, path: str) -> dict[str, Any]:
    hdr = doc.header
    acadver = hdr.get("$ACADVER", doc.dxfversion)
    insunits = int(hdr.get("$INSUNITS", 0) or 0)
    try:
        from ezdxf.units import unit_name
        units = unit_name(insunits)
    except Exception:
        units = str(insunits)
    info: dict[str, Any] = {
        "file": os.path.basename(path),
        "size_bytes": os.path.getsize(path),
        "dxf_version": acadver,
        "release": ACAD_RELEASE.get(acadver, "unknown"),
        "encoding": getattr(doc, "encoding", ""),
        "insunits": insunits,
        "units": units,
        "measurement": "metric" if hdr.get("$MEASUREMENT", 0) else "imperial",
    }
    ext_min, ext_max = hdr.get("$EXTMIN"), hdr.get("$EXTMAX")
    if ext_min is not None and ext_max is not None and all(abs(v) < 1e19 for v in list(ext_min) + list(ext_max)):
        info["extents"] = {"min": pt(ext_min), "max": pt(ext_max), "source": "header"}
    for key in ("$LIMMIN", "$LIMMAX", "$LTSCALE", "$DIMSCALE", "$TEXTSIZE"):
        val = hdr.get(key)
        if val is not None:
            info[key.lstrip("$").lower()] = plain(val)
    return info


def _layers(doc: Any) -> list[dict[str, Any]]:
    out = []
    for layer in doc.layers:
        try:
            rec = {
                "name": layer.dxf.name,
                "color": abs(int(_get(layer, "color", 7))),
                "linetype": _get(layer, "linetype", "Continuous"),
                "lineweight": _get(layer, "lineweight", -3),
                "on": not layer.is_off(),
                "frozen": bool(layer.is_frozen()),
                "locked": bool(layer.is_locked()),
                "plot": bool(_get(layer, "plot", 1)),
            }
            if layer.rgb is not None:
                rec["true_color"] = "#%02x%02x%02x" % tuple(layer.rgb)
            out.append(rec)
        except Exception as exc:
            log.warning("Bad layer entry skipped: %s", exc)
    return out


class _Collector:
    """Gathers records for one layout or block while counting everything."""

    def __init__(self, cap: int | None, want_geometry: bool):
        self.cap = cap
        self.want_geometry = want_geometry
        self.type_counts: Counter = Counter()
        self.layer_type_counts: dict[str, Counter] = defaultdict(Counter)
        self.texts: list = []
        self.inserts: list = []
        self.dimensions: list = []
        self.geometry: list = []
        self.truncated: Counter = Counter()

    def _add(self, bucket: list, name: str, make) -> None:
        if self.cap is not None and len(bucket) >= self.cap:
            self.truncated[name] += 1
            return
        bucket.append(make())


def _process(entity: Any, doc: Any, col: _Collector, errors: list, where: str) -> None:
    t = entity.dxftype()
    layer = _get(entity, "layer", "0")
    col.type_counts[t] += 1
    col.layer_type_counts[layer][t] += 1
    try:
        if t in TEXT_TYPES or t == "MULTILEADER":
            col._add(col.texts, "text", lambda: text_record(entity))
            if t == "MULTILEADER" and col.want_geometry:
                col._add(col.geometry, "geometry", lambda: geometry_record(entity))
        elif t in INSERT_TYPES:
            col._add(col.inserts, "inserts", lambda: insert_record(entity, doc))
        elif t in DIMENSION_TYPES:
            col._add(col.dimensions, "dimensions", lambda: dimension_record(entity))
        elif col.want_geometry:
            col._add(col.geometry, "geometry", lambda: geometry_record(entity))
    except Exception as exc:
        handle = _get(entity, "handle", "?")
        msg = f"{where}: {t} #{handle} skipped: {type(exc).__name__}: {exc}"
        log.warning(msg)
        if len(errors) < MAX_ERRORS_KEPT:
            errors.append(msg)


def _collect(entities: Iterable[Any], doc: Any, cap, want_geometry, errors, where) -> _Collector:
    col = _Collector(cap, want_geometry)
    iterator = iter(entities)
    while True:
        try:
            entity = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # broken entity database entry
            msg = f"{where}: entity iteration error: {exc}"
            log.warning(msg)
            if len(errors) < MAX_ERRORS_KEPT:
                errors.append(msg)
            break
        _process(entity, doc, col, errors, where)
    return col


def _collector_dict(col: _Collector) -> dict[str, Any]:
    return {
        "entity_count": sum(col.type_counts.values()),
        "type_counts": dict(col.type_counts.most_common()),
        "layer_type_counts": {k: dict(v.most_common()) for k, v in sorted(col.layer_type_counts.items())},
        "texts": col.texts,
        "inserts": col.inserts,
        "dimensions": col.dimensions,
        "geometry": col.geometry,
        "truncated": dict(col.truncated),
    }


def _layout_extra(layout: Any) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    try:
        d = layout.dxf_layout.dxf
        for key in ("paper_width", "paper_height", "plot_paper_units", "page_setup_name",
                    "paper_size", "plot_configuration_file"):
            v = d.get(key)
            if v not in (None, ""):
                extra[key] = plain(v)
    except Exception:
        pass
    return extra


def _block_records(doc: Any, cap, want_geometry, errors) -> list[dict[str, Any]]:
    blocks = []
    for block in doc.blocks:
        try:
            if block.is_any_layout:
                continue
            name = block.name
            blk = block.block
            info: dict[str, Any] = {
                "name": name,
                "base_point": pt(_get(blk, "base_point", (0, 0, 0))),
                "anonymous": name.startswith("*"),
                "xref": bool(getattr(blk, "is_xref", False)),
                "description": _get(block.block_record, "description", "") if block.block_record else "",
            }
            if info["xref"]:
                info["xref_path"] = _get(blk, "xref_path", "")
            # Dimension blocks (*D) duplicate DIMENSION data - count only.
            is_dim_block = name.upper().startswith("*D")
            attdefs = []
            entities = []
            col = _Collector(cap, want_geometry)
            for e in block:
                t = e.dxftype()
                try:
                    if t == "ATTDEF":
                        col.type_counts[t] += 1
                        attdefs.append({"tag": e.dxf.tag, "prompt": _get(e, "prompt", ""),
                                        "default": _attrib_text(e), "insert": pt(e.dxf.insert),
                                        "height": r(_get(e, "height", 0.0)),
                                        "invisible": bool(_get(e, "flags", 0) & 1),
                                        "constant": bool(_get(e, "flags", 0) & 2)})
                        continue
                except Exception as exc:
                    log.warning("Block %s: bad ATTDEF skipped: %s", name, exc)
                    continue
                if is_dim_block:
                    col.type_counts[t] += 1
                    continue
                _process(e, doc, col, errors, f"block {name}")
            d = _collector_dict(col)
            info.update(attdefs=attdefs, entity_count=d["entity_count"],
                        type_counts=d["type_counts"], texts=d["texts"], inserts=d["inserts"],
                        dimensions=d["dimensions"], geometry=d["geometry"],
                        truncated=d["truncated"], dimension_block=is_dim_block)
            blocks.append(info)
        except Exception as exc:
            msg = f"block {getattr(block, 'name', '?')} skipped: {exc}"
            log.warning(msg)
            if len(errors) < MAX_ERRORS_KEPT:
                errors.append(msg)
    return blocks


def _compute_extents(msp: Any, entity_count: int) -> dict[str, Any] | None:
    if entity_count > 200_000:
        return None
    try:
        from ezdxf import bbox
        box = bbox.extents(msp, fast=True)
        if box.has_data:
            return {"min": pt(box.extmin), "max": pt(box.extmax), "source": "computed"}
    except Exception as exc:
        log.debug("Extents computation failed: %s", exc)
    return None


def read_dxf(path: str, max_entities: int | None = None, geometry: bool = True,
             source_type: str = "DXF") -> dict[str, Any]:
    """Read a DXF file and return a dict with every piece of extracted data.

    max_entities caps each list (geometry, text, inserts, dimensions) per
    layout/block; counts are always complete.
    """
    log.info("Reading DXF %s", path)
    doc, errors = _load(path)
    info = _file_info(doc, path)
    info["source_type"] = source_type
    layers = _layers(doc)
    info["layer_count"] = len(layers)

    layouts = []
    msp = doc.modelspace()
    for layout in doc.layouts:
        try:
            is_model = layout.name.lower() == "model" or layout is msp or getattr(layout, "is_modelspace", False)
            col = _collect(layout, doc, max_entities, geometry, errors, f"layout {layout.name}")
            d = _collector_dict(col)
            d["name"] = layout.name
            d["kind"] = "model space" if is_model else "paper space"
            d.update(_layout_extra(layout))
            layouts.append(d)
        except Exception as exc:
            msg = f"layout {getattr(layout, 'name', '?')} skipped: {exc}"
            log.warning(msg)
            errors.append(msg)
    layouts.sort(key=lambda d: (d["kind"] != "model space", d["name"]))

    if "extents" not in info:
        msp_count = next((l["entity_count"] for l in layouts if l["kind"] == "model space"), 0)
        ext = _compute_extents(msp, msp_count)
        if ext:
            info["extents"] = ext

    blocks = _block_records(doc, max_entities, geometry, errors)

    total = Counter()
    for l in layouts:
        total.update(l["type_counts"])
    info["entity_count"] = sum(total.values())

    return {
        "kind": "dxf",
        "info": info,
        "layers": layers,
        "layouts": layouts,
        "blocks": blocks,
        "entity_type_totals": dict(total.most_common()),
        "options": {"max_entities": max_entities, "geometry": geometry},
        "errors": errors,
    }

