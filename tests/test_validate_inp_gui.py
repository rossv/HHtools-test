import sys

import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5 import QtWidgets

from hh_tools.gui.validate_inp_gui import ValidateInpWindow


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_gui_runs_with_python(qapp, monkeypatch, tmp_path):
    win = ValidateInpWindow()
    dummy = tmp_path / "a.inp"
    dummy.write_text("[JUNCTIONS]\n")
    win.files_edit.setText(str(dummy))
    win.range_check.setChecked(False)

    started = {}

    def fake_start(program, arguments):
        started["program"] = program
        started["arguments"] = list(arguments)

    monkeypatch.setattr(win.process, "start", fake_start)
    win._run()

    assert started["program"] == sys.executable
    assert started["arguments"][:2] == ["-m", "hh_tools.validate_inp"]
    assert str(dummy) in started["arguments"]
    assert "--no-range" in started["arguments"]
