"""PyQt5 front-end for :mod:`hh_tools.download_streamflow`."""

from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

try:  # Optional dependency for map preview
    from PyQt5 import QtWebEngineWidgets, QtWebChannel  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without web engine
    QtWebEngineWidgets = None  # type: ignore
    QtWebChannel = None  # type: ignore

from hh_tools.gui.theme import apply_dark_palette

ICON_DIR = Path(__file__).with_name("icons")


class _MapBridge(QtCore.QObject):
    """Bridge object allowing JS to notify Python of marker clicks."""

    stationClicked = QtCore.pyqtSignal(str)

    @QtCore.pyqtSlot(str)
    def markerClicked(self, sid: str) -> None:  # pragma: no cover - trivial slot
        self.stationClicked.emit(sid)


class StationSearchPanel(QtWidgets.QWidget):
    """Panel providing simple city-based station search."""

    station_selected = QtCore.pyqtSignal(str)
    message = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        search_layout = QtWidgets.QHBoxLayout()
        self.city_edit = QtWidgets.QLineEdit()
        self.search_btn = QtWidgets.QPushButton("Search")
        search_layout.addWidget(self.city_edit)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.list = QtWidgets.QListWidget()
        self.list.currentItemChanged.connect(self._current_changed)
        layout.addWidget(self.list)

        if QtWebEngineWidgets is not None:
            self.map_view = QtWebEngineWidgets.QWebEngineView()
            if QtWebChannel is not None:
                self._bridge = _MapBridge(self)
                self._bridge.stationClicked.connect(self._marker_chosen)
                channel = QtWebChannel.QWebChannel(self.map_view.page())
                channel.registerObject("bridge", self._bridge)
                self.map_view.page().setWebChannel(channel)
        else:  # pragma: no cover - WebEngine not available
            self.map_view = QtWidgets.QLabel("Map preview unavailable")
            self.map_view.setAlignment(QtCore.Qt.AlignCenter)
        self.map_view.setMinimumHeight(200)
        layout.addWidget(self.map_view)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self._buffer = ""
        self._stations: list[dict] = []
        self.search_process = QtCore.QProcess(self)
        self.search_process.readyReadStandardOutput.connect(self._handle_stdout)
        self.search_process.readyReadStandardError.connect(self._handle_stderr)
        self.search_process.finished.connect(self._search_finished)
        self.search_btn.clicked.connect(self._start_search)

    def _start_search(self) -> None:
        city = self.city_edit.text().strip()
        if not city:
            self.message.emit("Enter city before searching.")
            return
        self.message.emit(f"Searching stations near {city}...")
        self.list.clear()
        self._stations = []
        self._update_map([])
        self.progress.setVisible(True)
        code = (
            "import json,sys\n"
            "from hh_tools.download_streamflow import find_stations_by_city\n"
            "res = find_stations_by_city(sys.argv[1])\n"
            "print(json.dumps(res))\n"
        )
        args = ["-c", code, city]
        self._buffer = ""
        self.search_process.start(sys.executable, args)

    def _handle_stdout(self) -> None:
        self._buffer += bytes(self.search_process.readAllStandardOutput()).decode()

    def _handle_stderr(self) -> None:
        text = bytes(self.search_process.readAllStandardError()).decode().strip()
        if text:
            self.message.emit(text)

    def _search_finished(self) -> None:
        self.progress.setVisible(False)
        try:
            stations = json.loads(self._buffer or "[]")
        except Exception:
            stations = []
        self._stations = stations
        for st in stations:
            item = QtWidgets.QListWidgetItem(f"{st['id']} - {st.get('name', '')}")
            item.setData(QtCore.Qt.UserRole, st["id"])
            self.list.addItem(item)
        if not stations:
            self.message.emit("No stations found.")
        self._update_map(stations)

    def _current_changed(
        self, current: QtWidgets.QListWidgetItem | None, _prev: QtWidgets.QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        sid = current.data(QtCore.Qt.UserRole)
        self.station_selected.emit(sid)
        self._update_map(self._stations, selected=sid)

    def _marker_chosen(self, sid: str) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(QtCore.Qt.UserRole) == sid:
                self.list.setCurrentItem(item)
                break

    def _update_map(self, stations: list[dict], selected: str | None = None) -> None:
        """Render a map showing station locations."""
        if QtWebEngineWidgets is None:
            return  # Web engine support not available
        try:
            import folium
        except Exception:  # pragma: no cover - folium optional
            return

        pts = [
            (s.get("latitude"), s.get("longitude"), s.get("id"))
            for s in stations
            if s.get("latitude") is not None and s.get("longitude") is not None
        ]
        if not pts:
            self.map_view.setHtml("")
            return

        avg_lat = sum(p[0] for p in pts) / len(pts)
        avg_lon = sum(p[1] for p in pts) / len(pts)
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=8)
        markers = []
        for lat, lon, sid in pts:
            icon = folium.Icon(color="red") if sid == selected else None
            marker = folium.Marker([lat, lon], tooltip=sid, icon=icon)
            marker.add_to(m)
            markers.append((sid, marker.get_name()))

        html = io.StringIO()
        m.save(html, close_file=False)
        page = html.getvalue()

        if QtWebChannel is not None:
            lines = [
                '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>',
                "<script>",
                "var bridge;",
                "new QWebChannel(qt.webChannelTransport, function(channel){",
                "    bridge = channel.objects.bridge;",
                "});",
            ]
            for sid, name in markers:
                lines.append(
                    f"{name}.on('click', function(){{ if (bridge) bridge.markerClicked('{sid}'); }});"
                )
            lines.append("</script>")
            page = page.replace("</body>", "\n".join(lines) + "\n</body>")

        self.map_view.setHtml(page)


class DownloadStreamflowWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Download Streamflow")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "download_streamflow.ico")))

        apply_dark_palette(QtWidgets.QApplication.instance())

        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        main_layout = QtWidgets.QHBoxLayout(self)
        form_widget = QtWidgets.QWidget(self)
        form = QtWidgets.QFormLayout(form_widget)
        main_layout.addWidget(form_widget, 2)

        self.search_panel = StationSearchPanel(self)
        self.search_panel.station_selected.connect(self._station_chosen)
        self.search_panel.message.connect(self._append_output)
        main_layout.addWidget(self.search_panel, 3)

        self.station_edit = QtWidgets.QLineEdit(self.settings.value("station", ""))
        form.addRow("Station", self.station_edit)

        today = QtCore.QDate.currentDate()
        self.start_date = QtWidgets.QDateEdit(today)
        self.start_date.setCalendarPopup(True)
        self.start_date.setMaximumDate(today)
        self.end_date = QtWidgets.QDateEdit(today)
        self.end_date.setCalendarPopup(True)
        self.end_date.setMaximumDate(today)
        form.addRow("Start date", self.start_date)
        form.addRow("End date", self.end_date)

        self.parameter_edit = QtWidgets.QLineEdit("00060")
        form.addRow("Parameter", self.parameter_edit)

        self.output_edit = QtWidgets.QLineEdit(self.settings.value("output", ""))
        browse_out = QtWidgets.QPushButton("Browse")
        browse_out.clicked.connect(self._choose_output)
        out_layout = QtWidgets.QHBoxLayout()
        out_layout.addWidget(self.output_edit)
        out_layout.addWidget(browse_out)
        form.addRow("Output file", out_layout)

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["csv", "tsf", "swmm"])
        form.addRow("Format", self.format_combo)

        self.units_combo = QtWidgets.QComboBox()
        self.units_combo.addItems(["cfs", "m3/s"])
        form.addRow("Units", self.units_combo)

        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(self._show_help)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.help_btn)
        form.addRow(btn_layout)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        form.addRow(self.progress)

        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        form.addRow(self.output_box)

        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

    # ----------------------- util methods -----------------------
    def _station_chosen(self, sid: str) -> None:
        self.station_edit.setText(sid)

    def _choose_output(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Output file")
        if path:
            self.output_edit.setText(path)

    def _run(self) -> None:
        station = self.station_edit.text().strip()
        if not station:
            self._append_output("Station is required")
            return
        out = self.output_edit.text().strip()
        if not out:
            self._append_output("Output path is required")
            return
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")
        args = [
            "-m",
            "hh_tools.download_streamflow",
            "--station",
            station,
            "--start",
            start,
            "--end",
            end,
            "--output",
            out,
            "--format",
            self.format_combo.currentText(),
            "--parameter",
            self.parameter_edit.text().strip() or "00060",
            "--units",
            self.units_combo.currentText(),
        ]
        self.output_box.clear()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.process.start(sys.executable, args)
        self.progress.setVisible(True)

    def _handle_stdout(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode()
        self._append_output(text.rstrip())

    def _handle_stderr(self) -> None:
        text = bytes(self.process.readAllStandardError()).decode()
        self._append_output(text.rstrip())

    def _process_finished(self) -> None:
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)
        if os.environ.get("HH_LAUNCHER"):
            print("LAUNCHED", flush=True)

    def _append_output(self, text: str) -> None:
        if text:
            self.output_box.appendPlainText(text)

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self._append_output("Canceled")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _show_help(self) -> None:  # pragma: no cover - trivial wrapper
        QtWidgets.QMessageBox.information(self, "Help", "Enter station and dates then run.")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # pragma: no cover - GUI persistence
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("station", self.station_edit.text())
        self.settings.setValue("output", self.output_edit.text())
        super().closeEvent(event)


def main() -> None:  # pragma: no cover - GUI entry point
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = DownloadStreamflowWindow()
    win.show()
    app.exec_()
    if os.environ.get("HH_LAUNCHER"):
        print("LAUNCHED", flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()

