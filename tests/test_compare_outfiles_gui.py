import pytest

pytest.importorskip("PyQt5.QtWidgets")
pytest.importorskip("matplotlib")
from PyQt5 import QtWidgets

import hh_tools.gui.compare_outfiles_gui as cog


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_discover_ids_populates_list(qapp, monkeypatch):
    win = cog.CompareOutfilesWindow()
    try:
        win.file1_edit.setText("f1")
        win.file2_edit.setText("f2")
        win.type_combo.setCurrentText("node")
        monkeypatch.setattr(cog, "discover_ids", lambda f, t: ["A", "B"])
        win._discover_ids()
        assert [win.ids_list.list.item(i).text() for i in range(win.ids_list.list.count())] == [
            "A",
            "B",
        ]
    finally:
        win.close()


def test_discover_params_populates_list(qapp, monkeypatch):
    win = cog.CompareOutfilesWindow()
    try:
        win.file1_edit.setText("f1")
        win.file2_edit.setText("f2")
        win.type_combo.setCurrentText("node")
        monkeypatch.setattr(
            cog, "list_possible_params", lambda f, t: ["Flow", "Depth"]
        )
        win._discover_params()
        assert [
            win.params_list.list.item(i).text()
            for i in range(win.params_list.list.count())
        ] == ["Flow", "Depth"]
    finally:
        win.close()
