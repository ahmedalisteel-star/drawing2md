# sample_drawing.dxf

## Summary

- **Source:** DXF file `sample_drawing.dxf` (83,818 bytes)
- **DXF version:** AC1032 (R2018)
- **Units:** Millimeters ($INSUNITS = 4)
- **Extents (computed):** min (-40.3, -200.375) max (2400, 1249.26, 10) -> size 2440.3 x 1449.635
- **Layers:** 7
- **Layouts:** 2 (Model: 20 entities, Layout1: 2 entities)
- **Entities (all layouts):** 22
- **Top entity types:** DIMENSION 5, INSERT 2, TEXT 2, LINE 1, CIRCLE 1, ARC 1, LWPOLYLINE 1, POLYLINE 1, ELLIPSE 1, SPLINE 1
- **Block definitions:** 5 (+5 dimension blocks) | **Inserts:** 2 | **Attributes:** 3
- **Texts:** 4 | **Dimensions:** 5

## File info

| property | value |
|---|---|
| file | sample_drawing.dxf |
| size_bytes | 83818 |
| dxf_version | AC1032 |
| release | R2018 |
| encoding | cp1252 |
| insunits | 4 |
| units | Millimeters |
| measurement | metric |
| limmin | (0, 0) |
| limmax | (420, 297) |
| ltscale | 1 |
| dimscale | 1 |
| textsize | 2.5 |
| source_type | DXF |
| layer_count | 7 |
| entity_count | 22 |
| extents min | (-40.3, -200.375) |
| extents max | (2400, 1249.26, 10) |

## Layers

| name | color | linetype | lineweight | on | frozen | locked | plot | entities |
|---|---|---|---|---|---|---|---|---|
| 0 | 7 | Continuous | -3 | yes | no | no | yes | 2 |
| Defpoints | 7 | Continuous | -3 | yes | no | no | no | 0 |
| WALLS | 1 | Continuous | -3 | yes | no | no | yes | 10 |
| TEXT | 2 | Continuous | -3 | yes | no | no | yes | 3 |
| DIMS | 3 | Continuous | -3 | yes | no | no | yes | 5 |
| HIDDEN | 4 | Continuous | -3 | no | no | no | yes | 1 |
| FROZEN | 5 | Continuous | -3 | yes | yes | no | yes | 0 |

## Summary counts

| entity type | count |
|---|---|
| DIMENSION | 5 |
| INSERT | 2 |
| TEXT | 2 |
| LINE | 1 |
| CIRCLE | 1 |
| ARC | 1 |
| LWPOLYLINE | 1 |
| POLYLINE | 1 |
| ELLIPSE | 1 |
| SPLINE | 1 |
| POINT | 1 |
| HATCH | 1 |
| SOLID | 1 |
| 3DFACE | 1 |
| MTEXT | 1 |
| VIEWPORT | 1 |

### Model (model space) - entities per layer

| layer | total | by type |
|---|---|---|
| 0 | 1 | INSERT 1 |
| DIMS | 5 | DIMENSION 5 |
| HIDDEN | 1 | POINT 1 |
| TEXT | 3 | TEXT 1, MTEXT 1, INSERT 1 |
| WALLS | 10 | LINE 1, CIRCLE 1, ARC 1, LWPOLYLINE 1, POLYLINE 1, ELLIPSE 1, SPLINE 1, HATCH 1, SOLID 1, 3DFACE 1 |

### Layout1 (paper space) - entities per layer

| layer | total | by type |
|---|---|---|
| 0 | 1 | TEXT 1 |
| VIEWPORTS | 1 | VIEWPORT 1 |

## Text (4)

| where | type | layer | text | insert | height | rotation | style |
|---|---|---|---|---|---|---|---|
| Model | TEXT | TEXT | GROUND FLOOR PLAN | (10, 1200) | 50 | 0 | Standard |
| Model | MTEXT | TEXT | Steel grade S355<br>All bolts M20 8.8 | (10, 1100) | 25 | 0 | Standard |
| Layout1 | TEXT | 0 | SHEET 1 OF 1 | (10, 10) | 5 | 0 | Standard |
| block TITLE_BLOCK | TEXT | 0 | COMPANY | (5, 80) | 10 | 0 | Standard |

## Blocks & Attributes

### Block inserts (2)

| where | handle | block | layer | position | scale (x, y, z) | rotation | attributes |
|---|---|---|---|---|---|---|---|
| Model | A7 | TITLE_BLOCK | TEXT | (2000, 0) | (1, 1, 1) | 0 | DWG_NO=ST-101; REV=B |
| Model | B0 | MARK | 0 | (300, 300) | (2, 2, 1) | 45 | MARK=C1 |

### Attributes (3)

| where | block | insert handle | tag | value | position | layer |
|---|---|---|---|---|---|---|
| Model | TITLE_BLOCK | A7 | DWG_NO | ST-101 | (2005, 50) | 0 |
| Model | TITLE_BLOCK | A7 | REV | B | (2005, 30) | 0 |
| Model | MARK | B0 | MARK | C1 | (300, 300) | 0 |

### Attribute definitions - ATTDEF (3)

| block | tag | prompt | default | invisible | constant |
|---|---|---|---|---|---|
| TITLE_BLOCK | DWG_NO | Drawing number |  | no | no |
| TITLE_BLOCK | REV | Revision |  | no | no |
| MARK | MARK |  |  | no | no |

### Block definitions (5)

| name | base point | entities | types | attdefs | xref |
|---|---|---|---|---|---|
| _ARCHTICK | (0, 0) | 1 | LWPOLYLINE 1 |  |  |
| _CLOSEDFILLED | (0, 0) | 1 | SOLID 1 |  |  |
| _CLOSEDBLANK | (0, 0) | 1 | LWPOLYLINE 1 |  |  |
| TITLE_BLOCK | (0, 0) | 4 | ATTDEF 2, LWPOLYLINE 1, TEXT 1 | DWG_NO, REV |  |
| MARK | (0, 0) | 2 | CIRCLE 1, ATTDEF 1 | MARK |  |

#### Block `_ARCHTICK` entities

| # | type | layer | handle | details |
|---|---|---|---|---|
| 1 | LWPOLYLINE | 0 | 77 | closed: no; vertices: 2; points (x, y, b=bulge): (-0.5, -0.5) (0.5, 0.5) |

#### Block `_CLOSEDFILLED` entities

| # | type | layer | handle | details |
|---|---|---|---|---|
| 1 | SOLID | 0 | 7B | vertices: (-1, 0.164) (0, 0) (-1, -0.164) (-1, -0.164) |

#### Block `_CLOSEDBLANK` entities

| # | type | layer | handle | details |
|---|---|---|---|---|
| 1 | LWPOLYLINE | 0 | 87 | closed: yes; vertices: 3; points (x, y, b=bulge): (-1, 0.164) (0, 0) (-1, -0.164) |

#### Block `TITLE_BLOCK` entities

| # | type | layer | handle | details |
|---|---|---|---|---|
| 1 | TEXT | 0 | A4 | "COMPANY" at (5, 80) h=10 |
| 2 | LWPOLYLINE | 0 | A3 | closed: yes; vertices: 4; points (x, y, b=bulge): (0, 0) (400, 0) (400, 100) (0, 100) |

#### Block `MARK` entities

| # | type | layer | handle | details |
|---|---|---|---|---|
| 1 | CIRCLE | 0 | AE | center: (0, 0); radius: 5 |

## Dimensions (5)

Measurement is in drawing units (degrees for angular dimensions). Displayed text = measurement x DIMLFAC, rounded (DIMRND/DIMDEC), with R/Ø prefix and override text applied; "(computed)" means the dimension had no rendered block and the text was rebuilt.

| where | handle | type | layer | measurement | DIMLFAC | displayed text | override | dimstyle | points |
|---|---|---|---|---|---|---|---|---|---|
| Model | B3 | linear/rotated | DIMS | 1000 | 1 | 1000 | <> | EZDXF | defpoint=(0, -100); defpoint2=(0, 0); defpoint3=(1000, 0); text_midpoint=(500, -99.775) |
| Model | C2 | linear/rotated | DIMS | 500 | 1 | 500 | <> | EZDXF | defpoint=(-40, 30); defpoint2=(0, 0); defpoint3=(300, 400); text_midpoint=(109.82, 230.135) |
| Model | D1 | radius | DIMS | 250 | 1 | R250 | <> | EZ_RADIUS | defpoint=(500, 500); defpoint4=(676.777, 676.777); text_midpoint=(677.219, 677.537) |
| Model | DB | diameter | DIMS | 500 | 1 | Ø500 | <> | EZ_RADIUS | defpoint=(323.223, 676.777); defpoint4=(676.777, 323.223); text_midpoint=(677.537, 322.781) |
| Model | E5 | linear/rotated | DIMS | 500 | 1 | TYP. | TYP. | EZDXF | defpoint=(0, -200); defpoint2=(0, 0); defpoint3=(500, 0); text_midpoint=(250, -199.775) |

## Geometry

### Model (model space)

Layout settings: paper_width = 420, paper_height = 297, paper_size = A3

#### Layer `HIDDEN`

**POINT** (1)

| handle | location | color |
|---|---|---|
| 9A | (7, 8) | ByLayer |

#### Layer `WALLS`

**3DFACE** (1)

| handle | vertices | color |
|---|---|---|
| 9D | (0, 0) (10, 0) (10, 10, 5) (0, 10, 5) | ByLayer |

**ARC** (1)

| handle | center | radius | start angle | end angle | start pt | end pt | color |
|---|---|---|---|---|---|---|---|
| 91 | (0, 0) | 100 | 0 | 90 | (100, 0) | (0, 100) | ByLayer |

**CIRCLE** (1)

| handle | center | radius | color |
|---|---|---|---|
| 90 | (500, 500) | 250 | ByLayer |

**ELLIPSE** (1)

| handle | center | major axis | ratio | start param | end param | color |
|---|---|---|---|---|---|---|
| 98 | (200, 200) | (50, 0) | 0.5 | 0 | 6.283 | ByLayer |

**HATCH** (1)

| handle | pattern | solid | boundary | color |
|---|---|---|---|---|
| 9B | SOLID | yes | P1 polyline: (0, 0) (50, 0) (50, 50) (0, 50) / P2 edges: line (100, 0)-(150, 0); arc c=(125, 0) r=25 0..180 | 1 |

**LINE** (1)

| handle | start | end | length | color |
|---|---|---|---|---|
| 8F | (0, 0) | (1000.123, 0) | 1000.123 | ByLayer |

**LWPOLYLINE** (1)

| handle | closed | vertices | points (x, y, b=bulge) | color |
|---|---|---|---|---|
| 92 | yes | 4 | (0, 0) (100, 0 b=0.5) (100, 100) (0, 100) | ByLayer |

**POLYLINE** (1)

| handle | mode | closed | vertices | points | color |
|---|---|---|---|---|---|
| 93 | AcDb3dPolyline | no | 3 | (0, 0) (10, 10, 10) (20, 0, 5) | ByLayer |

**SOLID** (1)

| handle | vertices | color |
|---|---|---|
| 9C | (0, 0) (10, 0) (0, 10) (10, 10) | ByLayer |

**SPLINE** (1)

| handle | degree | closed | control points | fit points | color |
|---|---|---|---|---|---|
| 99 | 3 | no |  | (0, 0) (10, 20) (30, 10) (40, 40) | ByLayer |

### Layout1 (paper space)

Layout settings: paper_width = 420, paper_height = 297, paper_size = A3

#### Layer `VIEWPORTS`

**VIEWPORT** (1)

| handle | id | center | width | height | view center | view height | scale |
|---|---|---|---|---|---|---|---|
| F5 | 3 | (150, 100) | 200 | 150 | (500, 500) | 1500 | 1:10 |

---
*Generated offline by drawing2md 0.1.0 - no AI, no network. Coordinates rounded to 3 decimals.*

