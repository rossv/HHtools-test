import sys
import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5 import QtWidgets

from hh_tools.gui.resample_timeseries_gui import ResampleWindow


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_gui_starts_process(qapp, monkeypatch, tmp_path):
    win = ResampleWindow()
    try:
        dummy = tmp_path / "data.csv"
        dummy.write_text("time,value\n0,1\n")
        out = tmp_path / "out.csv"
        win.file_edit.setText(str(dummy))
        win.output_edit.setText(str(out))
        win.freq_edit.setText("15min")
        win.format_combo.setCurrentText("csv")
        started = {}

        def fake_start(program, arguments):
            started["program"] = program
            started["arguments"] = list(arguments)

        monkeypatch.setattr(win.process, "start", fake_start)
        win._run()
        assert started["program"] == sys.executable
        assert started["arguments"][:2] == ["-m", "hh_tools.resample_timeseries"]
        assert "--freq" in started["arguments"]
        assert "15min" in started["arguments"]
        assert "--output" in started["arguments"]
        assert str(out) in started["arguments"]
    finally:
        win.close()
