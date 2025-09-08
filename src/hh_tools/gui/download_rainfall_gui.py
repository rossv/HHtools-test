"""PyQt5 front-end for download_rainfall."""

from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from PyQt5 import QtCore, QtGui, QtWidgets

try:  # Optional dependency used for map preview
    from PyQt5 import QtWebEngineWidgets  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without web engine
    QtWebEngineWidgets = None

from hh_tools.gui.theme import apply_dark_palette

from ..download_rainfall import (
    available_datasets,
    available_datatypes,
)

ICON_DIR = Path(__file__).with_name("icons")


class DatasetFetcher(QtCore.QThread):
    dataset_ready = QtCore.pyqtSignal(str, list)

    def __init__(self, stations, token):
        super().__init__()
        self._stations = stations
        self._token = token

    def run(self):
        for st in self._stations:
            sid = st["id"]
            try:
                data = available_datasets(sid, self._token)
            except Exception:
                data = []
            self.dataset_ready.emit(sid, data)


class StationSearchPanel(QtWidgets.QWidget):
    station_selected = QtCore.pyqtSignal(str, list)
    message = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        search_layout = QtWidgets.QHBoxLayout()
        self.city_edit = QtWidgets.QLineEdit()
        self.search_btn = QtWidgets.QPushButton("Search")
        search_layout.addWidget(self.city_edit)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.list = QtWidgets.QListWidget()
        self.list.setMaximumHeight(120)
        self.list.itemDoubleClicked.connect(self._list_chosen)
        self.list.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self.list)

        if QtWebEngineWidgets is not None:
            self.map_view = QtWebEngineWidgets.QWebEngineView()
        else:  # pragma: no cover - WebEngine not available
            self.map_view = QtWidgets.QLabel("Map preview unavailable")
            self.map_view.setAlignment(QtCore.Qt.AlignCenter)
        self.map_view.setMinimumHeight(200)
        layout.addWidget(self.map_view)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Dataset", "Earliest", "Latest"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        layout.addWidget(self.table)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.token = ""
        self._stations: dict[str, dict] = {}
        self._search_buffer = ""
        self.search_process = QtCore.QProcess(self)
        self.search_process.readyReadStandardOutput.connect(self._search_handle_stdout)
        self.search_process.readyReadStandardError.connect(self._search_handle_stderr)
        self.search_process.finished.connect(self._search_finished)
        self.search_btn.clicked.connect(self._start_search)

    def set_token(self, token: str) -> None:
        self.token = token

    def _start_search(self):
        city = self.city_edit.text().strip()
        if not city or not self.token:
            self.message.emit("Enter city and API key before searching.")
            return
        self.message.emit(f"Searching stations near {city}...")
        self.list.clear()
        self.table.setRowCount(0)
        self._update_map([])
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        code = (
            "import json, sys\n"
            "from hh_tools.download_rainfall import find_stations_by_city\n"
            "token, query = sys.argv[1:3]\n"
            "headers = {'token': token}\n"
            "res = find_stations_by_city(query, headers)\n"
            "if not res:\n"
            "    print('No stations found, expanding search radius...', file=sys.stderr)\n"
            "    res = find_stations_by_city(query, headers, buffer=1.0)\n"
            "print(json.dumps(res))\n"
        )
        args = ["-c", code, self.token, city]
        self._search_buffer = ""
        self.search_process.start(sys.executable, args)

    def _search_handle_stdout(self):
        data = bytes(self.search_process.readAllStandardOutput()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self._search_buffer += data

    def _search_handle_stderr(self):
        data = bytes(self.search_process.readAllStandardError()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.message.emit(data.rstrip())

    def _search_finished(self, code: int, _status: QtCore.QProcess.ExitStatus):
        self.progress.setVisible(False)
        if code != 0:
            self.message.emit("Station search failed.")
            return
        try:
            stations = json.loads(self._search_buffer or "[]")
        except Exception as e:
            self.message.emit(str(e))
            return
        if not stations:
            self.message.emit("No stations found.")
            self._update_map([])
            return
        self.list.clear()
        self._stations = {s["id"]: dict(s) for s in stations}
        self.progress.setRange(0, len(stations))
        self.progress.setValue(0)
        for st in stations:
            item = self._make_item(st)
            self.list.addItem(item)
        self.progress.setVisible(True)
        self._update_map(stations)
        self._fetcher = DatasetFetcher(stations, self.token)
        self._fetcher.dataset_ready.connect(self._dataset_ready)
        self._fetcher.finished.connect(lambda: self.progress.setVisible(False))
        self._fetcher.start()

    def _update_map(self, stations: List[dict]) -> None:
        """Render a simple map showing station locations."""
        if QtWebEngineWidgets is None:
            return  # Web engine support not available
        try:
            import folium
        except Exception:  # pragma: no cover - folium optional
            return

        if not stations:
            self.map_view.setHtml("")
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
        for lat, lon, sid in pts:
            folium.Marker([lat, lon], tooltip=sid).add_to(m)
        html = io.StringIO()
        m.save(html, close_file=False)
        self.map_view.setHtml(html.getvalue())

    def _format_item_text(self, st: dict) -> str:
        return (
            f"{st['id']} — {st.get('name','')} ("
            f"{st.get('mindate','?')} to {st.get('maxdate','?')}; "
            f"{st.get('datacoverage',0):.0%})"
        )

    def _apply_item_style(self, item: QtWidgets.QListWidgetItem, st: dict) -> None:
        coverage = st.get("datacoverage") or 0
        mindate, maxdate = st.get("mindate"), st.get("maxdate")
        years = 0
        try:
            years = (
                datetime.fromisoformat(maxdate) - datetime.fromisoformat(mindate)
            ).days / 365.25
        except Exception:
            pass
        f = item.font()
        f.setBold(coverage >= 0.9 or years >= 10)
        item.setFont(f)

    def _make_item(self, st: dict) -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem(self._format_item_text(st))
        self._apply_item_style(item, st)
        item.setData(QtCore.Qt.UserRole, st["id"])
        return item

    def _selection_changed(self, current, _prev):
        if current is None:
            return
        sid = current.data(QtCore.Qt.UserRole)
        st = self._stations.get(sid, {})
        self._populate_table(st.get("datasets") or [])

    def _populate_table(self, datasets):
        self.table.setRowCount(0)
        for d in datasets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = f"{d['id']} - {d.get('name','')}" if d.get("name") else d["id"]
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(d.get("mindate", "")))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(d.get("maxdate", "")))

    def _dataset_ready(self, sid: str, datasets: list):
        st = self._stations.get(sid)
        if st is None:
            return
        st["datasets"] = datasets
        tip = (
            "\n".join(
                f"{d['id']}: {d.get('mindate','?')} to {d.get('maxdate','?')}"
                for d in datasets
            )
            or "No datasets"
        )

        ds_dates = [
            (d.get("mindate"), d.get("maxdate"))
            for d in datasets
            if d.get("mindate") and d.get("maxdate")
        ]
        if ds_dates:
            st["mindate"] = min(d[0] for d in ds_dates)
            st["maxdate"] = max(d[1] for d in ds_dates)

        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(QtCore.Qt.UserRole) == sid:
                item.setToolTip(tip)
                item.setText(self._format_item_text(st))
                self._apply_item_style(item, st)
                break
        if (
            self.list.currentItem()
            and self.list.currentItem().data(QtCore.Qt.UserRole) == sid
        ):
            self._populate_table(datasets)
        self.progress.setValue(self.progress.value() + 1)

    def _list_chosen(self, item):
        sid = item.data(QtCore.Qt.UserRole)
        st = self._stations.get(sid, {})
        datasets = st.get("datasets") or []
        self.station_selected.emit(sid, datasets)


class DownloadRainfallWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Download Rainfall")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "download_rainfall.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        main_layout = QtWidgets.QHBoxLayout(self)
        form_widget = QtWidgets.QWidget(self)
        form = QtWidgets.QFormLayout(form_widget)
        main_layout.addWidget(form_widget, 2)
        self.search_panel = StationSearchPanel(self)
        main_layout.addWidget(self.search_panel, 3)

        # --- Station ---
        self.station_edit = QtWidgets.QLineEdit(self.settings.value("station", ""))
        self.station_edit.setToolTip("Station identifier")
        self.station_edit.editingFinished.connect(self._populate_datasets)
        form.addRow("Station", self.station_edit)

        # --- Dates ---
        today = QtCore.QDate.currentDate()
        self.start_date = QtWidgets.QDateEdit(today)
        self.start_date.setCalendarPopup(True)
        self.start_date.setMaximumDate(today)
        self.end_date = QtWidgets.QDateEdit(today)
        self.end_date.setCalendarPopup(True)
        self.end_date.setMaximumDate(today)
        form.addRow("Start date", self.start_date)
        form.addRow("End date", self.end_date)

        btn_yesterday = QtWidgets.QPushButton("Yesterday")
        btn_yesterday.clicked.connect(self._set_yesterday)
        btn_last_week = QtWidgets.QPushButton("Last Week")
        btn_last_week.clicked.connect(self._set_last_week)
        btn_last_month = QtWidgets.QPushButton("Last Month")
        btn_last_month.clicked.connect(self._set_last_month)
        shortcut_layout = QtWidgets.QHBoxLayout()
        shortcut_layout.addWidget(btn_yesterday)
        shortcut_layout.addWidget(btn_last_week)
        shortcut_layout.addWidget(btn_last_month)
        form.addRow("Quick dates", shortcut_layout)

        # --- API key ---
        self.api_edit = QtWidgets.QLineEdit()
        self.api_edit.setToolTip("API key for NOAA service")
        self.api_edit.setText(self.settings.value("api_key", ""))
        self.api_save = QtWidgets.QCheckBox("Remember key")
        self.api_save.setChecked(bool(self.settings.value("api_key", "")))
        api_layout = QtWidgets.QHBoxLayout()
        api_layout.addWidget(self.api_edit)
        api_layout.addWidget(self.api_save)
        form.addRow("API key", api_layout)

        # --- Source ---
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems(
            ["Demo (no API key required)", "NOAA (requires free token)"]
        )
        self.source_combo.setCurrentIndex(1)
        form.addRow("Source", self.source_combo)

        self.dataset_combo = QtWidgets.QComboBox()
        self.dataset_combo.currentIndexChanged.connect(self._dataset_changed)
        form.addRow("Dataset", self.dataset_combo)

        self.datatype_combo = QtWidgets.QComboBox()
        form.addRow("Datatype", self.datatype_combo)

        # --- Output ---
        self.output_edit = QtWidgets.QLineEdit(self.settings.value("output_path", ""))
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
        self.units_combo.addItems(["mm", "in"])
        form.addRow("Units", self.units_combo)

        # --- Buttons ---
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

        # --- Progress & Output ---
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        form.addRow(self.progress)

        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        form.addRow(self.output_box)

        # Process
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)
        self.search_panel.station_selected.connect(self._station_chosen)
        self.search_panel.message.connect(self.output_box.appendPlainText)
        self.api_edit.textChanged.connect(self.search_panel.set_token)
        self.search_panel.set_token(self.api_edit.text().strip())

        # Fetching datasets requires a network request which can block the GUI
        # if executed during widget construction.  Delay the initial population
        # until the event loop has started so the window appears responsive even
        # when the request is slow or times out.
        QtCore.QTimer.singleShot(0, self._populate_datasets)

    # --- Date helpers ---
    def _set_yesterday(self):
        d = QtCore.QDate.currentDate().addDays(-1)
        self.start_date.setDate(d)
        self.end_date.setDate(d)

    def _set_last_week(self):
        today = QtCore.QDate.currentDate()
        start_this_week = today.addDays(-today.dayOfWeek() + 1)
        start = start_this_week.addDays(-7)
        self.start_date.setDate(start)
        self.end_date.setDate(start.addDays(6))

    def _set_last_month(self):
        today = QtCore.QDate.currentDate()
        first_this_month = QtCore.QDate(today.year(), today.month(), 1)
        start = first_this_month.addMonths(-1)
        end = first_this_month.addDays(-1)
        self.start_date.setDate(start)
        self.end_date.setDate(end)

    # --- Run ---
    def _choose_output(self):
        start = self.settings.value("output_path", self.settings.value("last_dir", ""))
        filters = (
            "CSV files (*.csv);;TSF files (*.tsf);;SWMM files (*.inp);;All files (*.*)"
        )
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select output file", start, filters
        )
        if path:
            if selected_filter.startswith("CSV") and not path.endswith(".csv"):
                path += ".csv"
            elif selected_filter.startswith("TSF") and not path.endswith(".tsf"):
                path += ".tsf"
            elif selected_filter.startswith("SWMM") and not path.endswith(".inp"):
                path += ".inp"
            self.output_edit.setText(path)
            self.settings.setValue("output_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _run(self):
        station = self.station_edit.text().strip()
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")
        api = self.api_edit.text().strip()
        outp = self.output_edit.text().strip()

        if not all([station, start, end, outp]):
            QtWidgets.QMessageBox.warning(
                self, "Missing parameters", "Fill all required fields."
            )
            return

        today = QtCore.QDate.currentDate()
        if self.end_date.date() > today:
            QtWidgets.QMessageBox.warning(
                self, "Invalid End Date", "End date cannot be after today."
            )
            return

        if self.api_save.isChecked():
            self.settings.setValue("api_key", api)

        self.settings.setValue("station", station)

        data = self.dataset_combo.currentData()
        dataset = data.get("id") if isinstance(data, dict) else data
        datatype = self.datatype_combo.currentData()
        if not dataset or not datatype:
            QtWidgets.QMessageBox.warning(
                self, "Missing parameters", "Select dataset and datatype."
            )
            return

        args = [
            "--station",
            station,
            "--start",
            start,
            "--end",
            end,
            "--api-key",
            api,
            "--output",
            outp,
            "--format",
            self.format_combo.currentText(),
            "--units",
            self.units_combo.currentText(),
            "--source",
            "noaa" if "NOAA" in self.source_combo.currentText() else "example",
            "--dataset",
            dataset,
            "--datatype",
            datatype,
        ]

        self.output_box.appendPlainText(
            f"Fetching rainfall data for {station} ({start} → {end})"
        )
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.process.start(sys.executable, ["-m", "hh_tools.download_rainfall", *args])

    def _populate_datasets(self) -> None:
        api = self.api_edit.text().strip()
        station = self.station_edit.text().strip()
        if not api or not station:
            return
        try:
            datasets = available_datasets(station, api)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", str(e))
            return
        self._populate_dataset_combo(datasets)

    def _populate_dataset_combo(self, datasets):
        self.dataset_combo.clear()
        self.datatype_combo.clear()
        for d in datasets:
            label = f"{d['id']} - {d.get('name','')}" if d.get("name") else d["id"]
            self.dataset_combo.addItem(label, d)
        if datasets:
            self.dataset_combo.setCurrentIndex(0)
            self._dataset_changed()

    def _dataset_changed(self):
        data = self.dataset_combo.currentData()
        if not data:
            return
        mindate = data.get("mindate")
        maxdate = data.get("maxdate")
        min_q = (
            QtCore.QDate.fromString(mindate, "yyyy-MM-dd")
            if mindate
            else QtCore.QDate(1900, 1, 1)
        )
        max_q = (
            QtCore.QDate.fromString(maxdate, "yyyy-MM-dd")
            if maxdate
            else QtCore.QDate.currentDate()
        )
        self.start_date.setMinimumDate(min_q)
        self.end_date.setMinimumDate(min_q)
        self.start_date.setMaximumDate(max_q)
        self.end_date.setMaximumDate(max_q)
        if self.start_date.date() < min_q:
            self.start_date.setDate(min_q)
        if self.end_date.date() < min_q:
            self.end_date.setDate(min_q)
        if self.start_date.date() > max_q:
            self.start_date.setDate(max_q)
        if self.end_date.date() > max_q:
            self.end_date.setDate(max_q)
        self._populate_datatypes()

    def _populate_datatypes(self) -> None:
        api = self.api_edit.text().strip()
        station = self.station_edit.text().strip()
        data = self.dataset_combo.currentData()
        dataset = data.get("id") if isinstance(data, dict) else None
        if not api or not station or not dataset:
            return
        try:
            dtypes = available_datatypes(station, dataset, api)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", str(e))
            return
        self.datatype_combo.clear()
        for dt_id, dt_name in dtypes:
            label = f"{dt_id} - {dt_name}" if dt_name else dt_id
            self.datatype_combo.addItem(label, dt_id)

    def _station_chosen(self, sid: str, datasets: list):
        self.station_edit.setText(sid)
        self._populate_dataset_combo(datasets)

    def _handle_stdout(self):
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.output_box.appendPlainText(data.rstrip())

    def _handle_stderr(self):
        data = bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.output_box.appendPlainText(data.rstrip())

    def _process_finished(self, code: int, _status: QtCore.QProcess.ExitStatus):
        if code == 0:
            self.output_box.appendPlainText("✅ Download complete\n")
        elif code == 2:
            self.output_box.appendPlainText("⚠️ No rainfall data was returned\n")
            QtWidgets.QMessageBox.information(
                self,
                "No Data Found",
                "No rainfall data was returned for the chosen station/date/datatype.\n\n"
                "Suggestions:\n"
                " • Try a different station (some report intermittently)\n"
                " • Expand your date range\n"
                " • Check if NOAA has published the latest data yet",
            )
        else:
            self.output_box.appendPlainText("❌ Download failed\n")
            QtWidgets.QMessageBox.warning(
                self,
                "Download Failed",
                "The download failed due to an error (bad station ID, invalid token, or network issue).",
            )
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("output_path", self.output_edit.text())
        self.settings.setValue("station", self.station_edit.text())
        super().closeEvent(event)

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _show_help(self):
        QtWidgets.QMessageBox.information(
            self,
            "Download Rainfall",
            "Select a data source, enter station ID and date range, then provide your API key.\n\n"
            "NOAA tokens: https://www.ncdc.noaa.gov/cdo-web/token\n"
            "Use the panel on the right to search for station IDs.",
        )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = DownloadRainfallWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
