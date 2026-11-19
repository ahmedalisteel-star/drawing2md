# drawing2md

**Convert PDF, DXF and DWG drawings into Markdown, one `.md` file per drawing.**

`drawing2md` reads engineering and CAD drawings and writes out everything it finds as
structured Markdown that a person can read and an AI can take in: geometry, vectors,
blocks, attributes, text, dimensions, layers, tables and images. You can also get a
full `.json` dump.

> **100% offline. No AI. No API calls. No network access of any kind.**
> Every step runs on your own machine with open-source Python libraries
> ([ezdxf](https://github.com/mozman/ezdxf), [PyMuPDF](https://github.com/pymupdf/PyMuPDF)),
> plus two optional local programs (ODA File Converter for DWG, Tesseract for OCR).
> Your drawings never leave your computer.

---

## What it extracts

### DXF / DWG

| Section | Content |
|---|---|
| **File info** | DXF version/release, units (`$INSUNITS`), extents, limits, encoding, layer count |
| **Layers** | name, color, linetype, lineweight, on/off, frozen, locked, plot, entity count |
| **Summary counts** | entity counts by type, and by layer x type for every layout |
| **Text** | TEXT and MTEXT (MTEXT formatting codes cleaned): text, position, height, rotation, style, layer, including text inside block definitions |
| **Blocks & Attributes** | every block definition (name, base point, entity list, ATTDEFs), every INSERT (block, position, scale, rotation, layer, dynamic-block real name) and every ATTRIB tag = value (title blocks, mark numbers) |
| **Dimensions** | type, measured value, displayed text exactly as drawn (rebuilt from DIMLFAC, DIMRND, DIMDEC, DIMZIN, DIMPOST, R/Ø prefix and the `<>` override placeholder when the dimension has no rendered block), override text, dimstyle, definition points |
| **Geometry (per layer)** | LINE (start/end/length), ARC/CIRCLE (center, radius, angles), LWPOLYLINE/POLYLINE (vertices, closed, bulges), ELLIPSE, SPLINE (control/fit points), POINT, HATCH (boundary paths), SOLID/TRACE/3DFACE, VIEWPORT, LEADER, MLINE, IMAGE, and a full attribute dump for any other entity type |
| **Layouts** | model space and every paper-space layout are reported separately |

### PDF

| Section | Content |
|---|---|
| **Per page** | size in pt and mm, rotation, status (text layer / scanned / blank) |
| **Text** | every text line with bounding box, font and size |
| **Vector paths** | lines, rectangles, quads and Bezier curves with coordinates, stroke color, fill and line width |
| **Tables** | detected tables written as Markdown tables |
| **Images** | size, color space, position on the page; saved to `<name>_images/` |
| **Scanned pages** | pages with no text layer are OCR'd with Tesseract if it is installed, otherwise marked `scanned - OCR not available` |
| **PDF layers** | optional-content groups (CAD layers exported to PDF) |

---

## Install (Windows)

1. **Python 3.10 or newer** from <https://www.python.org/downloads/>. Tick **"Add python.exe to PATH"** during setup.

2. **Install drawing2md** (PowerShell or Command Prompt):

   ```powershell
   pip install git+https://github.com/ahmedalisteel-star/drawing2md.git
   ```

   Or from a local clone:

   ```powershell
   git clone https://github.com/ahmedalisteel-star/drawing2md.git
   cd drawing2md
   pip install -e ".[ocr,dev]"
   ```

3. **For DWG files: ODA File Converter** (free). Download it from
   <https://www.opendesign.com/guestfiles/oda_file_converter> and install it with the
   default options. drawing2md finds it automatically in
   `C:\Program Files\ODA\ODAFileConverter <version>\`. If you installed it somewhere else, use
   `--oda-path "D:\Tools\ODA\ODAFileConverter.exe"` or set the `ODA_FILE_CONVERTER` environment variable.

4. **Optional, for scanned PDFs: Tesseract OCR.** Install it from
   <https://github.com/UB-Mannheim/tesseract/wiki> (default folder
   `C:\Program Files\Tesseract-OCR\` is detected automatically), then:

   ```powershell
   pip install pytesseract Pillow
   ```

   For Arabic or other languages, tick the extra language data during the Tesseract
   setup and run with `--ocr-lang eng+ara`.

### Linux

```bash
pip install git+https://github.com/ahmedalisteel-star/drawing2md.git
sudo apt install tesseract-ocr          # optional OCR
pip install pytesseract Pillow          # optional OCR
# DWG: install the ODA File Converter .deb/.rpm from opendesign.com;
# on a headless server run it under xvfb:  xvfb-run drawing2md file.dwg
```

---

## Usage

```text
drawing2md input.dxf                  -> input.md next to the file
drawing2md input.pdf -o out/          -> out/input.md  (+ out/input_images/)
drawing2md drawing.dwg                -> drawing.md  (converted locally via ODA)
drawing2md folder/                    -> converts every PDF/DXF/DWG inside
drawing2md folder/ -r -o md/          -> include sub-folders, mirror them under md/
drawing2md a.dxf b.pdf -o result/     -> several files at once
drawing2md plan.dxf -o plan_notes.md  -> choose the output file name
```

| Option | Meaning |
|---|---|
| `-o, --output PATH` | output folder (or a `.md` file name for a single input). Default: next to each input |
| `--json` | also write a full `.json` dump with every extracted value |
| `--no-geometry` | skip geometry/vector-path tables (text, blocks, attributes, dimensions and tables are still extracted) |
| `--max-entities N` | cap each listed table at N rows per layout/block/page; counts stay complete (for huge files) |
| `-r, --recursive` | search folders recursively |
| `--oda-path EXE` | path to `ODAFileConverter.exe` |
| `--no-ocr` | never OCR scanned pages |
| `--ocr-lang LANG` | Tesseract languages, e.g. `eng`, `eng+ara` (default `eng`) |
| `--no-images` | list PDF images without saving them |
| `--no-tables` | skip PDF table detection (faster on very dense pages) |
| `-v` / `-q` | verbose / quiet |

If a folder contains `plan.dxf` and `plan.pdf`, the outputs are named `plan_dxf.md` and
`plan_pdf.md` so neither overwrites the other.

Also available as `python -m drawing2md ...`.

### Big files

* Entity counts are always complete. `--max-entities` only limits how many rows are listed.
* One broken entity is logged as a warning (listed at the end of the `.md`) and skipped.
  Damaged DXF files are retried with ezdxf's recover mode.
* In a batch, a file that fails is reported and the rest carry on (exit code 1 if anything failed).
* Markdown is written to disk line by line. A 50 MB DXF with 320,000 entities takes about 15 s
  with `--max-entities 5000` and about 21 s in full on a normal laptop.

### Use from Python

```python
from drawing2md.dxf_reader import read_dxf
from drawing2md.pdf_reader import read_pdf
from drawing2md.md_writer import render_markdown

data = read_dxf("plan.dxf", max_entities=1000)
print(data["layouts"][0]["inserts"][0]["attribs"])   # title block attributes
print(render_markdown(data)[:2000])
```

---

## Sample output

From `examples/sample_drawing.dxf` (generated by the test suite). The full files are in
[`examples/`](examples/).

```markdown
# sample_drawing.dxf

## Summary

- **Source:** DXF file `sample_drawing.dxf` (83,818 bytes)
- **DXF version:** AC1032 (R2018)
- **Units:** Millimeters ($INSUNITS = 4)
- **Extents (computed):** min (-40.3, -200.375) max (2400, 1249.26, 10) -> size 2440.3 x 1449.635
- **Layers:** 7
- **Layouts:** 2 (Model: 20 entities, Layout1: 2 entities)
- **Entities (all layouts):** 22
- **Top entity types:** DIMENSION 5, INSERT 2, TEXT 2, LINE 1, CIRCLE 1, ARC 1, LWPOLYLINE 1, ...
- **Block definitions:** 5 (+5 dimension blocks) | **Inserts:** 2 | **Attributes:** 3
- **Texts:** 4 | **Dimensions:** 5

## Text (4)

| where | type | layer | text | insert | height | rotation | style |
|---|---|---|---|---|---|---|---|
| Model | TEXT | TEXT | GROUND FLOOR PLAN | (10, 1200) | 50 | 0 | Standard |
| Model | MTEXT | TEXT | Steel grade S355<br>All bolts M20 8.8 | (10, 1100) | 25 | 0 | Standard |
| Layout1 | TEXT | 0 | SHEET 1 OF 1 | (10, 10) | 5 | 0 | Standard |
| block TITLE_BLOCK | TEXT | 0 | COMPANY | (5, 80) | 10 | 0 | Standard |

### Attributes (3)

| where | block | insert handle | tag | value | position | layer |
|---|---|---|---|---|---|---|
| Model | TITLE_BLOCK | A7 | DWG_NO | ST-101 | (2005, 50) | 0 |
| Model | TITLE_BLOCK | A7 | REV | B | (2005, 30) | 0 |
| Model | MARK | B0 | MARK | C1 | (300, 300) | 0 |

## Dimensions (5)

| where | handle | type | layer | measurement | DIMLFAC | displayed text | override | dimstyle | points |
|---|---|---|---|---|---|---|---|---|---|
| Model | D1 | radius | DIMS | 250 | 1 | R250 | <> | EZ_RADIUS | defpoint=(500, 500); defpoint4=(676.777, 676.777); ... |
| Model | DB | diameter | DIMS | 500 | 1 | Ø500 | <> | EZ_RADIUS | defpoint=(323.223, 676.777); defpoint4=(676.777, 323.223); ... |
| Model | E5 | linear/rotated | DIMS | 500 | 1 | TYP. | TYP. | EZDXF | defpoint=(0, -200); defpoint2=(0, 0); defpoint3=(500, 0); ... |

## Geometry

### Model (model space)

#### Layer `WALLS`

**LWPOLYLINE** (1)

| handle | closed | vertices | points (x, y, b=bulge) | color |
|---|---|---|---|---|
| 92 | yes | 4 | (0, 0) (100, 0 b=0.5) (100, 100) (0, 100) | ByLayer |
```

PDF tables come out as real Markdown tables:

```markdown
**Table 1** - 3 rows x 3 cols, bbox (450, 300, 810, 375)

| MARK | SECTION | QTY |
|---|---|---|
| B1 | HEA200 | 4 |
| C1 | HEB300 | 6 |
```

---

## Development

```powershell
git clone https://github.com/ahmedalisteel-star/drawing2md.git
cd drawing2md
pip install -e ".[ocr,dev]"
pytest
```

The tests build their own small DXF and PDF files with ezdxf and PyMuPDF, so the repo
holds no third-party drawings. The OCR and DWG round-trip tests run only when Tesseract or
the ODA File Converter is installed; otherwise they are skipped.

Project layout:

```text
drawing2md/
  cli.py            command line, batch handling, output naming
  dxf_reader.py     DXF -> dict (ezdxf)
  dwg_converter.py  DWG -> DXF via local ODA File Converter
  pdf_reader.py     PDF -> dict (PyMuPDF, optional Tesseract OCR)
  md_writer.py      dict -> Markdown / JSON
tests/              pytest suite (generates its own sample files)
examples/           sample inputs and their Markdown output
```

## License

Apache License 2.0. Copyright 2026 Ahmed Ali. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

drawing2md depends on, but does not bundle, PyMuPDF, which is licensed under the
GNU AGPL v3 (or a commercial license from Artifex). If you redistribute drawing2md
together with PyMuPDF, for example inside a packaged application or a network service,
check that you meet PyMuPDF's license terms.
