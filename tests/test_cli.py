import json
import shutil
import subprocess
import sys

from drawing2md.cli import main


def test_dxf_next_to_input(sample_dxf, tmp_path):
    assert main([sample_dxf, "-q"]) == 0
    md = tmp_path / "sample.md"
    assert md.is_file()
    assert "## Summary" in md.read_text(encoding="utf-8")


def test_pdf_to_output_folder_with_json(sample_pdf, tmp_path):
    out = tmp_path / "out"
    assert main([sample_pdf, "-o", str(out), "--json", "--no-ocr", "-q"]) == 0
    assert (out / "sample.md").is_file()
    data = json.loads((out / "sample.json").read_text(encoding="utf-8"))
    assert data["kind"] == "pdf"
    assert any((out / "sample_images").iterdir())


def test_output_md_filename(sample_dxf, tmp_path):
    target = tmp_path / "named" / "result.md"
    assert main([sample_dxf, "-o", str(target), "-q"]) == 0
    assert target.is_file()


def test_folder_converts_all_and_avoids_name_clash(tmp_path):
    from conftest import make_sample_dxf, make_sample_pdf

    folder = tmp_path / "drawings"
    folder.mkdir()
    make_sample_dxf(folder / "plan.dxf")
    make_sample_pdf(folder / "plan.pdf")
    make_sample_dxf(folder / "other.dxf")
    (folder / "notes.txt").write_text("ignored")
    out = tmp_path / "out"
    assert main([str(folder), "-o", str(out), "--no-ocr", "-q"]) == 0
    names = sorted(p.name for p in out.glob("*.md"))
    assert names == ["other.md", "plan_dxf.md", "plan_pdf.md"]


def test_recursive_folder(tmp_path):
    from conftest import make_sample_dxf

    sub = tmp_path / "proj" / "sub"
    sub.mkdir(parents=True)
    make_sample_dxf(sub / "deep.dxf")
    out = tmp_path / "out"
    assert main([str(tmp_path / "proj"), "-o", str(out), "-q"]) == 1  # nothing at top level
    assert main([str(tmp_path / "proj"), "-o", str(out), "-r", "-q"]) == 0
    assert (out / "sub" / "deep.md").is_file()


def test_options_no_geometry_and_max_entities(sample_dxf, tmp_path):
    out = tmp_path / "o"
    assert main([sample_dxf, "-o", str(out), "--no-geometry", "-q"]) == 0
    md = (out / "sample.md").read_text(encoding="utf-8")
    assert "_Skipped (--no-geometry)._" in md
    assert main([sample_dxf, "-o", str(out), "--max-entities", "1", "-q"]) == 0
    md = (out / "sample.md").read_text(encoding="utf-8")
    assert "capped by --max-entities" in md


def test_missing_input_and_bad_args(tmp_path, capsys):
    assert main([str(tmp_path / "nope.dxf")]) == 2
    assert main([str(tmp_path), "--max-entities", "0"]) == 2


def test_corrupt_file_does_not_stop_batch(tmp_path, capsys):
    from conftest import make_sample_dxf

    folder = tmp_path / "mix"
    folder.mkdir()
    (folder / "a_bad.pdf").write_bytes(b"not a pdf at all")
    make_sample_dxf(folder / "b_good.dxf")
    assert main([str(folder), "-q"]) == 1
    assert (folder / "b_good.md").is_file()
    assert "FAILED" in capsys.readouterr().err


def test_console_entry_point_runs(sample_dxf):
    exe = shutil.which("drawing2md")
    cmd = [exe] if exe else [sys.executable, "-m", "drawing2md"]
    res = subprocess.run(cmd + ["--version"], capture_output=True, text=True)
    assert res.returncode == 0 and "drawing2md" in res.stdout
