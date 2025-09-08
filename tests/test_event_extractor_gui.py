import sys
import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5 import QtWidgets

from hh_tools.gui.event_extractor_gui import EventExtractorWindow


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_gui_starts_process(qapp, monkeypatch, tmp_path):
    win = EventExtractorWindow()
    try:
        dummy = tmp_path / "rain.csv"
        dummy.write_text("time,value\n0,1\n")
        output_dir = tmp_path / "out"
        win.file_edit.setText(str(dummy))
        win.output_dir_edit.setText(str(output_dir))
        win.threshold_spin.setValue(0.1)
        win.duration_spin.setValue(10)
        started = {}

        def fake_start(program, arguments):
            started["program"] = program
            started["arguments"] = list(arguments)

        monkeypatch.setattr(win.process, "start", fake_start)
        win._run()
        assert started["program"] == sys.executable
        assert started["arguments"][:2] == ["-m", "hh_tools.event_extractor"]
        assert str(dummy) in started["arguments"]
        assert "--output-dir" in started["arguments"]
    finally:
        win.close()
