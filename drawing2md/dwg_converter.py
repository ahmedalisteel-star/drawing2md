"""Convert DWG to DXF with the free ODA File Converter (installed separately).

The converter runs locally; nothing is uploaded anywhere.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile

log = logging.getLogger("drawing2md")

ODA_DOWNLOAD_URL = "https://www.opendesign.com/guestfiles/oda_file_converter"
ENV_VAR = "ODA_FILE_CONVERTER"


class OdaNotFoundError(RuntimeError):
    """Raised when the ODA File Converter executable cannot be found."""

    def __init__(self, detail: str = ""):
        msg = (
            "ODA File Converter was not found, so DWG files cannot be read.\n"
            f"  Download it free from: {ODA_DOWNLOAD_URL}\n"
            "  Then either install it in the default folder "
            r"(C:\Program Files\ODA\ODAFileConverter <version>)"
            "\n  or pass --oda-path \"C:\\path\\to\\ODAFileConverter.exe\""
            f"\n  or set the {ENV_VAR} environment variable."
        )
        if detail:
            msg = f"{detail}\n{msg}"
        super().__init__(msg)


class DwgConversionError(RuntimeError):
    """Raised when ODA ran but no DXF was produced."""


def _version_key(path: str) -> tuple:
    digits = []
    for part in os.path.basename(os.path.dirname(path)).replace("ODAFileConverter", "").split("."):
        part = part.strip()
        digits.append(int(part) if part.isdigit() else 0)
    return tuple(digits)


def _candidates() -> list[str]:
    found: list[str] = []
    if sys.platform.startswith("win"):
        roots = {os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 r"C:\Program Files"}
        for root in roots:
            pattern = os.path.join(root, "ODA", "ODAFileConverter*", "ODAFileConverter.exe")
            found.extend(sorted(glob.glob(pattern), key=_version_key, reverse=True))
    else:
        for pattern in ("/usr/bin/ODAFileConverter", "/usr/local/bin/ODAFileConverter",
                        "/opt/ODAFileConverter*/ODAFileConverter",
                        "/usr/bin/ODAFileConverter_*/ODAFileConverter"):
            found.extend(sorted(glob.glob(pattern), reverse=True))
    return found


def find_oda(oda_path: str | None = None) -> str:
    """Return the path of ODAFileConverter or raise OdaNotFoundError."""
    if oda_path:
        if os.path.isdir(oda_path):
            exe = "ODAFileConverter.exe" if sys.platform.startswith("win") else "ODAFileConverter"
            oda_path = os.path.join(oda_path, exe)
        if os.path.isfile(oda_path):
            return oda_path
        raise OdaNotFoundError(f"--oda-path does not exist: {oda_path}")

    env = os.environ.get(ENV_VAR)
    if env and os.path.isfile(env):
        return env

    for name in ("ODAFileConverter", "ODAFileConverter.exe"):
        which = shutil.which(name)
        if which:
            return which

    for cand in _candidates():
        if os.path.isfile(cand):
            return cand
    raise OdaNotFoundError()


def convert_dwg_to_dxf(dwg_path: str, out_dir: str, oda_path: str | None = None,
                       dxf_version: str = "ACAD2018", timeout: int = 600) -> str:
    """Convert one DWG to DXF inside out_dir and return the DXF path."""
    exe = find_oda(oda_path)
    dwg_path = os.path.abspath(dwg_path)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(dwg_path))[0]

    # ODA converts whole folders, so give it a private input folder with one file.
    with tempfile.TemporaryDirectory(prefix="drawing2md_in_") as in_dir:
        local = os.path.join(in_dir, stem + ".dwg")
        shutil.copy2(dwg_path, local)
        cmd = [exe, in_dir, out_dir, dxf_version, "DXF", "0", "1", "*.DWG"]
        log.info("Converting DWG with ODA: %s", os.path.basename(dwg_path))
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise DwgConversionError(f"ODA File Converter timed out after {timeout}s") from exc
        except OSError as exc:
            raise OdaNotFoundError(f"Could not start ODA File Converter: {exc}") from exc

    dxf = os.path.join(out_dir, stem + ".dxf")
    if not os.path.isfile(dxf):
        matches = [p for p in glob.glob(os.path.join(out_dir, "*.dxf"))
                   if os.path.splitext(os.path.basename(p))[0].lower() == stem.lower()]
        if matches:
            dxf = matches[0]
    if not os.path.isfile(dxf):
        err_files = glob.glob(os.path.join(out_dir, "*.err"))
        detail = ""
        for ef in err_files:
            try:
                with open(ef, encoding="utf-8", errors="replace") as fh:
                    detail += fh.read().strip() + "\n"
            except OSError:
                pass
        detail = detail or (proc.stderr or proc.stdout or "").strip()
        hint = ""
        if not sys.platform.startswith("win") and not os.environ.get("DISPLAY"):
            hint = " (on headless Linux run it under xvfb-run)"
        raise DwgConversionError(f"ODA produced no DXF for {dwg_path}{hint}. {detail}".strip())
    return dxf
