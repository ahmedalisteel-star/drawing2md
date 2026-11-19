"""Command-line interface: drawing2md <file-or-folder> [...]."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import time
from typing import Iterator

from . import SUPPORTED_EXTENSIONS, __version__
from .dwg_converter import DwgConversionError, OdaNotFoundError, convert_dwg_to_dxf, find_oda
from .md_writer import write_json, write_markdown

log = logging.getLogger("drawing2md")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="drawing2md",
        description="Convert PDF, DXF and DWG drawings into Markdown (one .md per input). "
                    "Runs 100%% offline - no AI, no API calls.",
    )
    ap.add_argument("inputs", nargs="+", metavar="INPUT",
                    help="PDF/DXF/DWG file(s) or folder(s)")
    ap.add_argument("-o", "--output", metavar="PATH",
                    help="output folder (or a .md file name when converting a single file); "
                         "default: next to each input")
    ap.add_argument("--json", action="store_true", help="also write a full .json dump")
    ap.add_argument("--no-geometry", action="store_true",
                    help="skip geometry / vector-path tables (text, blocks, attributes, "
                         "dimensions and tables are still extracted)")
    ap.add_argument("--max-entities", type=int, metavar="N", default=None,
                    help="cap each listed table at N rows per layout/block/page (counts stay complete)")
    ap.add_argument("-r", "--recursive", action="store_true", help="search folders recursively")
    ap.add_argument("--oda-path", metavar="EXE", help="path to ODAFileConverter(.exe) for DWG files")
    ap.add_argument("--no-ocr", action="store_true", help="never run OCR on scanned PDF pages")
    ap.add_argument("--ocr-lang", default="eng", help="Tesseract language(s), e.g. eng or eng+ara")
    ap.add_argument("--no-images", action="store_true", help="list PDF images but do not save them")
    ap.add_argument("--no-tables", action="store_true", help="skip PDF table detection (faster)")
    ap.add_argument("-v", "--verbose", action="store_true", help="show debug messages")
    ap.add_argument("-q", "--quiet", action="store_true", help="only show errors")
    ap.add_argument("--version", action="version", version=f"drawing2md {__version__}")
    return ap


def iter_inputs(paths: list[str], recursive: bool) -> Iterator[tuple[str, str]]:
    """Yield (file, base_folder) pairs; base_folder keeps sub-folder structure."""
    for raw in paths:
        path = os.path.abspath(raw)
        if os.path.isdir(path):
            if recursive:
                for root, dirs, files in os.walk(path):
                    dirs[:] = sorted(d for d in dirs if not d.endswith("_images"))
                    for name in sorted(files):
                        if name.lower().endswith(SUPPORTED_EXTENSIONS):
                            yield os.path.join(root, name), path
            else:
                for name in sorted(os.listdir(path)):
                    full = os.path.join(path, name)
                    if os.path.isfile(full) and name.lower().endswith(SUPPORTED_EXTENSIONS):
                        yield full, path
        elif os.path.isfile(path):
            yield path, os.path.dirname(path)
        else:
            raise FileNotFoundError(raw)


def output_paths(src: str, base: str, output: str | None, single: bool) -> tuple[str, str]:
    """Return (md_path, out_dir) for one input file."""
    stem = os.path.splitext(os.path.basename(src))[0]
    if output and single and output.lower().endswith(".md"):
        md = os.path.abspath(output)
        return md, os.path.dirname(md)
    if output:
        rel = os.path.relpath(os.path.dirname(src), base)
        out_dir = os.path.abspath(os.path.join(output, rel)) if rel != "." else os.path.abspath(output)
    else:
        out_dir = os.path.dirname(src)
    return os.path.join(out_dir, stem + ".md"), out_dir


def plan_outputs(files: list[tuple[str, str]], output: str | None, single: bool) -> list[str]:
    """Pick one .md path per input; plan.dxf + plan.pdf -> plan_dxf.md + plan_pdf.md."""
    paths = [output_paths(src, base, output, single)[0] for src, base in files]
    seen: dict[str, int] = {}
    for p in paths:
        key = os.path.normcase(p)
        seen[key] = seen.get(key, 0) + 1
    result = []
    for (src, _), p in zip(files, paths):
        if seen[os.path.normcase(p)] > 1:
            ext = os.path.splitext(src)[1].lstrip(".").lower()
            p = os.path.splitext(p)[0] + f"_{ext}.md"
        result.append(p)
    return result


def convert_file(src: str, md_path: str, args: argparse.Namespace) -> dict:
    """Convert one input file; returns the extracted data dict."""
    out_dir = os.path.dirname(md_path)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(md_path))[0]
    ext = os.path.splitext(src)[1].lower()
    geometry = not args.no_geometry

    if ext == ".pdf":
        from .pdf_reader import read_pdf
        images_dir = None if args.no_images else os.path.join(out_dir, stem + "_images")
        data = read_pdf(src, max_entities=args.max_entities, geometry=geometry,
                        images_dir=images_dir, ocr=not args.no_ocr, ocr_lang=args.ocr_lang,
                        tables=not args.no_tables)
    elif ext == ".dxf":
        from .dxf_reader import read_dxf
        data = read_dxf(src, max_entities=args.max_entities, geometry=geometry)
    elif ext == ".dwg":
        from .dxf_reader import read_dxf
        with tempfile.TemporaryDirectory(prefix="drawing2md_dwg_") as tmp:
            dxf = convert_dwg_to_dxf(src, tmp, oda_path=args.oda_path)
            data = read_dxf(dxf, max_entities=args.max_entities, geometry=geometry, source_type="DWG")
        data["info"]["file"] = os.path.basename(src)
        data["info"]["size_bytes"] = os.path.getsize(src)
        data["info"]["converted_from"] = os.path.basename(src)
    else:
        raise ValueError(f"unsupported file type: {ext}")

    write_markdown(data, md_path)
    if args.json:
        write_json(data, os.path.splitext(md_path)[0] + ".json")
    return data


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    # ezdxf is chatty on damaged files; keep its own logger quieter unless -v.
    logging.getLogger("ezdxf").setLevel(logging.DEBUG if args.verbose else logging.ERROR)

    if args.max_entities is not None and args.max_entities < 1:
        print("error: --max-entities must be >= 1", file=sys.stderr)
        return 2

    try:
        files = list(iter_inputs(args.inputs, args.recursive))
    except FileNotFoundError as exc:
        print(f"error: input not found: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("No PDF, DXF or DWG files found.", file=sys.stderr)
        return 1

    if any(f.lower().endswith(".dwg") for f, _ in files):
        try:
            find_oda(args.oda_path)
        except OdaNotFoundError as exc:
            print(f"warning: {exc}", file=sys.stderr)

    single = len(files) == 1
    targets = plan_outputs(files, args.output, single)
    failures = 0
    for (src, base), md_path in zip(files, targets):
        t0 = time.perf_counter()
        try:
            data = convert_file(src, md_path, args)
        except (OdaNotFoundError, DwgConversionError) as exc:
            failures += 1
            print(f"FAILED {src}\n  {exc}", file=sys.stderr)
            continue
        except Exception as exc:  # never let one file stop a batch
            failures += 1
            log.debug("Traceback", exc_info=True)
            print(f"FAILED {src}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        warn = f", {len(data['errors'])} warnings" if data.get("errors") else ""
        if not args.quiet:
            print(f"OK  {src} -> {md_path} ({time.perf_counter() - t0:.1f}s{warn})")

    if not args.quiet and len(files) > 1:
        print(f"Done: {len(files) - failures} converted, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
