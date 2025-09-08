import json
import os
import subprocess
import sys
from pathlib import Path

from hh_tools.validate_inp import validate_file


def write_inp(tmp_path, text: str):
    path = tmp_path / "model.inp"
    path.write_text(text.strip() + "\n")
    return path


def test_valid_file(tmp_path):
    content = """
    [JUNCTIONS]
    J1 0 10
    J2 0 12
    [OUTFALLS]
    O1 0 FREE
    [CONDUITS]
    C1 J1 O1 100
    C2 J1 J2 200
    """
    path = write_inp(tmp_path, content)
    rep = validate_file(str(path))
    assert rep["errors"] == []
    assert rep["warnings"] == []

    result = subprocess.run(
        [sys.executable, "-m", "hh_tools.validate_inp", str(path), "--json"],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")},
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    data = json.loads(output.split(": ", 1)[1])
    assert data[0]["errors"] == []


def test_missing_section(tmp_path):
    content = """
    [JUNCTIONS]
    J1 0 10
    [CONDUITS]
    C1 J1 O1 100
    """
    path = write_inp(tmp_path, content)
    rep = validate_file(str(path))
    assert any("Missing [OUTFALLS]" in e["message"] for e in rep["errors"])


def test_cross_reference(tmp_path):
    content = """
    [JUNCTIONS]
    J1 0 10
    [OUTFALLS]
    O1 0 FREE
    [CONDUITS]
    C1 J1 J2 100
    """
    path = write_inp(tmp_path, content)
    rep = validate_file(str(path))
    assert any("unknown node" in e["message"] for e in rep["errors"])


def test_range_toggle(tmp_path):
    content = """
    [JUNCTIONS]
    J1 0 -5
    [OUTFALLS]
    O1 0 FREE
    [CONDUITS]
    C1 J1 O1 -10
    """
    path = write_inp(tmp_path, content)
    rep = validate_file(str(path))
    assert any("Negative" in e["message"] for e in rep["errors"])
    assert any("Non-positive" in e["message"] for e in rep["errors"])

    rep2 = validate_file(str(path), check_ranges=False)
    assert rep2["errors"] == []

