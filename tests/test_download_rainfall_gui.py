import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5 import QtWidgets

from hh_tools.gui.download_rainfall_gui import StationSearchPanel


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_dataset_ready_updates_dates(qapp):
    panel = StationSearchPanel()
    try:
        station = {
            "id": "S1",
            "name": "Test",
            "mindate": "1700-01-01",
            "maxdate": "2100-01-01",
            "datacoverage": 1.0,
        }
        panel._stations = {station["id"]: station}
        panel.list.addItem(panel._make_item(station))
        datasets = [
            {
                "id": "GHCND",
                "name": "Daily",
                "mindate": "2000-01-01",
                "maxdate": "2020-01-01",
            }
        ]
        panel._dataset_ready("S1", datasets)
        assert panel._stations["S1"]["mindate"] == "2000-01-01"
        assert panel._stations["S1"]["maxdate"] == "2020-01-01"
        text = panel.list.item(0).text()
        assert "2000-01-01" in text and "2020-01-01" in text
    finally:
        panel.deleteLater()
