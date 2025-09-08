import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5 import QtWidgets, QtCore

from hh_tools.gui.extract_timeseries_gui import ExtractorWindow


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_selected_id_counts(qapp):
    win = ExtractorWindow()
    try:
        win.id_lists["node"].set_items(["N1", "N2"])
        win.id_lists["link"].set_items(["L1"])
        win._update_id_counts()
        # select some
        win.id_lists["node"].list.item(0).setCheckState(QtCore.Qt.Checked)
        win.id_lists["link"].list.item(0).setCheckState(QtCore.Qt.Checked)
        qapp.processEvents()
        text = win.id_count_label.text()
        assert "Nodes: 1" in text
        assert "Links: 1" in text
        assert "Total: 2" in text
    finally:
        win.close()


def test_auto_discover_triggered_on_new_file(qapp, tmp_path):
    """Adding a new .out file should trigger ID discovery automatically."""
    win = ExtractorWindow()
    try:
        called = []

        def fake_start(auto=False):
            called.append(auto)

        # Replace discovery method; existing signal uses attribute lookup at call time
        win._start_discover_ids = fake_start

        f = tmp_path / "test.out"
        f.write_text("")

        win.file_list.add_files([str(f)])
        assert called == [True]

        # Adding the same file again should not re-trigger discovery
        win.file_list.add_files([str(f)])
        assert called == [True]
    finally:
        win.close()
