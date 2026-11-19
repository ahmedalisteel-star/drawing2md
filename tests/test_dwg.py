import os
import subprocess
import sys

import pytest

from drawing2md import dwg_converter
from drawing2md.cli import main
from drawing2md.dwg_converter import ODA_DOWNLOAD_URL, OdaNotFoundError, find_oda


def _oda():
    try:
        return find_oda()
    except OdaNotFoundError:
        return None


def test_bad_oda_path_gives_download_link(tmp_path):
    with pytest.raises(OdaNotFoundError) as exc:
        find_oda(str(tmp_path / "missing" / "ODAFileConverter.exe"))
    assert ODA_DOWNLOAD_URL in str(exc.value)


def test_oda_not_installed_message(monkeypatch):
    monkeypatch.delenv(dwg_converter.ENV_VAR, raising=False)
    monkeypatch.setattr(dwg_converter.shutil, "which", lambda name: None)
    monkeypatch.setattr(dwg_converter, "_candidates", lambda: [])
    with pytest.raises(OdaNotFoundError) as exc:
        find_oda()
    assert "--oda-path" in str(exc.value)


def test_cli_reports_missing_oda(tmp_path, capsys):
    dwg = tmp_path / "x.dwg"
    dwg.write_bytes(b"AC1032 fake")
    rc = main([str(dwg), "--oda-path", str(tmp_path / "none.exe")])
    assert rc == 1
    assert ODA_DOWNLOAD_URL in capsys.readouterr().err


@pytest.mark.skipif(_oda() is None, reason="ODA File Converter not installed")
def test_dwg_roundtrip(sample_dxf, tmp_path):
    """DXF -> DWG with ODA, then drawing2md reads the DWG back."""
    oda = _oda()
    src_dir, dwg_dir = tmp_path / "src", tmp_path / "dwg"
    src_dir.mkdir()
    dwg_dir.mkdir()
    os.replace(sample_dxf, src_dir / "plan.dxf")
    kwargs = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
    subprocess.run([oda, str(src_dir), str(dwg_dir), "ACAD2018", "DWG", "0", "1", "*.DXF"],
                   capture_output=True, timeout=300, **kwargs)
    dwg = dwg_dir / "plan.dwg"
    if not dwg.is_file():
        pytest.skip("ODA could not create a DWG in this environment")
    out = tmp_path / "out"
    assert main([str(dwg), "-o", str(out), "--json", "-q"]) == 0
    md = (out / "plan.md").read_text(encoding="utf-8")
    assert "DWG file `plan.dwg`" in md
    assert "ST-101" in md and "GROUND FLOOR PLAN" in md
