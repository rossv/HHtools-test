from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")
from hh_tools.gui.batch_runner_gui import extract_prev_runtime


def test_extract_prev_runtime(tmp_path: Path) -> None:
    inp = tmp_path / "scenario.inp"
    inp.write_text(";")
    rpt = tmp_path / "scenario.rpt"
    rpt.write_text("some text\n Total elapsed time: 00:05:13\n")

    assert extract_prev_runtime(inp) == "00:05:13"

    missing = tmp_path / "missing.inp"
    assert extract_prev_runtime(missing) is None

