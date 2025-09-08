"""Design Storm GUI - Beta presets, NOAA auto-refresh; compact layout; results table; theme-aware plots (white labels)."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from string import Template

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
try:
    from geopy.geocoders import Nominatim
except Exception:  # pragma: no cover - optional dependency
    Nominatim = None  # type: ignore[assignment]
    _GEOCODER = None
else:  # pragma: no cover - handled via tests
    _GEOCODER = Nominatim(user_agent="hh_tools")

try:
    from PyQt5 import QtWebEngineWidgets
except ImportError:
    QtWebEngineWidgets = None


try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except ModuleNotFoundError as e:  # pragma: no cover - handled at runtime
    FigureCanvas = Figure = None  # type: ignore[assignment]
    _MATPLOTLIB_ERROR = e
else:
    _MATPLOTLIB_ERROR = None

PKG_ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.append(str(PKG_ROOT))

from hh_tools.design_storm import _label_to_minutes, build_storm, fetch_noaa_table
from hh_tools.gui.theme import apply_dark_palette

ICON_DIR = Path(__file__).with_name("icons")
DISTRIBUTIONS = [
    "scs_type_i",
    "scs_type_ia",
    "scs_type_ii",
    "scs_type_iii",
    "huff_q1",
    "huff_q2",
    "huff_q3",
    "huff_q4",
    "user",
]
EXPORTS = [
    ("Intensity (in/hr)", "intensity"),
    ("Volume (in)", "volume"),
    ("Cumulative (in)", "cumulative"),
]

MAX_PLOT_BARS = 2500
TARGET_MAX_BINS = 10000

# ----------------------------------------------------------------------
# Leaflet map (auto-refresh NOAA when the pin moves)
# ----------------------------------------------------------------------
if QtWebEngineWidgets is not None:
    MAP_HTML = Template(
        """<!DOCTYPE html>
<html><head>
<meta charset='utf-8'/>
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self' https://unpkg.com;
  img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com;
  style-src 'self' 'unsafe-inline' https://unpkg.com;
  script-src 'self' 'unsafe-inline' https://unpkg.com;">
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>
<style>html,body,#map{height:100%;margin:0}</style>
<script>
var map, marker;
function initMap(lat, lon){
  map = L.map('map').setView([lat, lon], 9);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {subdomains:'abc', maxZoom:19, crossOrigin:true, attribution:'&copy; OpenStreetMap contributors'}
  ).addTo(map);
  marker = L.marker([lat, lon], {draggable:true}).addTo(map);
  marker.on('dragend', function(e){
    var p=e.target.getLatLng();
    console.log('CLICK:'+p.lat+','+p.lng);
  });
  map.on('click', function(e){
    marker.setLatLng(e.latlng);
    console.log('CLICK:'+e.latlng.lat+','+e.latlng.lng);
  });
}
function setMarker(lat, lon){ if(marker){ marker.setLatLng([lat,lon]); map.panTo([lat,lon]); } }
</script></head>
<body onload='initMap($lat, $lon)'><div id='map'></div></body></html>"""
    )

    class MapPage(QtWebEngineWidgets.QWebEnginePage):
        moved = QtCore.pyqtSignal(float, float)

        def __init__(self, lat_edit, lon_edit, parent=None):
            super().__init__(parent)
            self.lat_edit = lat_edit
            self.lon_edit = lon_edit

        def javaScriptConsoleMessage(self, level, msg, line, source):
            if msg.startswith("CLICK:"):
                lat, lon = msg[6:].split(",")
                # Let textChanged fire (debounced NOAA refresh)
                self.lat_edit.setText(lat)
                self.lon_edit.setText(lon)
                self.moved.emit(float(lat), float(lon))
            else:
                super().javaScriptConsoleMessage(level, msg, line, source)

    class MapView(QtWebEngineWidgets.QWebEngineView):
        def __init__(self, lat_edit, lon_edit):
            super().__init__()
            self.lat_edit = lat_edit
            self.lon_edit = lon_edit
            page = MapPage(lat_edit, lon_edit, self)
            self.setPage(page)
            page.moved.connect(lambda *_: None)
            self._load()
            self.lat_edit.textChanged.connect(self._changed)
            self.lon_edit.textChanged.connect(self._changed)

        def _load(self):
            try:
                lat = float(self.lat_edit.text())
                lon = float(self.lon_edit.text())
            except Exception:
                lat = 40.44
                lon = -79.995
            self.setHtml(
                MAP_HTML.substitute(lat=lat, lon=lon), QtCore.QUrl("https://local")
            )

        def _changed(self):
            try:
                lat = float(self.lat_edit.text())
                lon = float(self.lon_edit.text())
            except Exception:
                return
            self.page().runJavaScript(f"setMarker({lat},{lon});")


# ----------------------------------------------------------------------
# NOAA worker
# ----------------------------------------------------------------------
class NOAAThread(QtCore.QThread):
    table = QtCore.pyqtSignal(object)

    def __init__(self, lat: float, lon: float):
        super().__init__()
        self.lat = lat
        self.lon = lon

    def run(self):
        try:
            df = fetch_noaa_table(self.lat, self.lon)
        except Exception:
            df = None
        self.table.emit(df)


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------
class DesignStormWindow(QtWidgets.QWidget):
    def __init__(self):
        if _MATPLOTLIB_ERROR is not None:
            raise ModuleNotFoundError(
                "matplotlib is required to run the Design Storm tool"
            ) from _MATPLOTLIB_ERROR
        super().__init__()
        self.setWindowTitle("Design Storm Generator")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "design_storm.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)
        self._df_noaa = None
        self._last_dist = "scs_type_ii"
        self._in_interp = False
        self._busy_count = 0

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        main = QtWidgets.QHBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.addWidget(splitter)

        # ---------- LEFT: controls ----------
        left = QtWidgets.QWidget()
        left_v = QtWidgets.QVBoxLayout(left)
        left_v.setContentsMargins(4, 4, 4, 4)
        left_v.setSpacing(6)

        # Location (tidy Lat/Lon spacing)
        gb_loc = QtWidgets.QGroupBox("Location")
        gv = QtWidgets.QGridLayout(gb_loc)
        gv.setHorizontalSpacing(10)
        gv.setVerticalSpacing(6)
        self.lat_edit = QtWidgets.QLineEdit("40.4406")
        self.lon_edit = QtWidgets.QLineEdit("-79.9959")
        self.addr_edit = QtWidgets.QLineEdit()
        self.addr_edit.setPlaceholderText("Address or place name")
        for w in (self.lat_edit, self.lon_edit):
            w.setMaximumWidth(150)
            w.setAlignment(QtCore.Qt.AlignRight)
        gv.addWidget(QtWidgets.QLabel("Lat"), 0, 0)
        gv.addWidget(self.lat_edit, 0, 1)
        gv.addWidget(QtWidgets.QLabel("Lon"), 0, 2)
        gv.addWidget(self.lon_edit, 0, 3)
        gv.addWidget(QtWidgets.QLabel("Address"), 1, 0)
        gv.addWidget(self.addr_edit, 1, 1, 1, 3)
        self.addr_edit.editingFinished.connect(self._geocode_address)
        gv.setColumnStretch(4, 1)

        # Map
        self.map_group = QtWidgets.QGroupBox("Map")
        map_layout = QtWidgets.QVBoxLayout(self.map_group)
        if QtWebEngineWidgets is not None:
            self.map_view = MapView(self.lat_edit, self.lon_edit)
            self.map_view.setMinimumHeight(220)
            map_layout.addWidget(self.map_view)
        else:
            map_layout.addWidget(
                QtWidgets.QLabel("Install PyQtWebEngine to enable mapping.")
            )

        # NOAA table (even columns; auto-refreshed)
        gb_noaa = QtWidgets.QGroupBox("NOAA Atlas 14 (mean depth)")
        nv = QtWidgets.QVBoxLayout(gb_noaa)
        nv.setSpacing(6)
        self.noaa_table = QtWidgets.QTableWidget()
        self.noaa_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.noaa_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.noaa_table.setAlternatingRowColors(True)
        self.noaa_table.setMinimumHeight(150)
        self.noaa_table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        hh = self.noaa_table.horizontalHeader()
        hh.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)  # evenly distribute
        nv.addWidget(self.noaa_table)
        tip = QtWidgets.QLabel(
            "Click a cell to apply Return Period, Depth, and Duration. When unlocked, edits interpolate from this table."
        )
        tip.setStyleSheet("color:#888;font-size:11px;")
        nv.addWidget(tip)

        # Storm Parameters split into two columns
        gb_params = QtWidgets.QGroupBox("Storm Parameters")
        params_h = QtWidgets.QHBoxLayout(gb_params)
        params_h.setSpacing(12)

        # LEFT COLUMN (lockable) + lock checkbox at the top
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(6)
        self.use_noaa_chk = QtWidgets.QCheckBox("Use NOAA selection (lock parameters)")
        self.use_noaa_chk.setChecked(True)
        left_col.addWidget(self.use_noaa_chk)
        lock_form = QtWidgets.QFormLayout()
        lock_form.setHorizontalSpacing(10)
        lock_form.setVerticalSpacing(6)

        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(0.05, 1e6)
        self.duration_spin.setValue(6.0)
        self.duration_spin.setSuffix(" hr")
        self.rp_spin = QtWidgets.QDoubleSpinBox()
        self.rp_spin.setRange(1, 1e6)
        self.rp_spin.setDecimals(3)
        self.rp_spin.setValue(10.0)
        self.depth_spin = QtWidgets.QDoubleSpinBox()
        self.depth_spin.setRange(0.000, 1e4)
        self.depth_spin.setDecimals(3)
        self.depth_spin.setSuffix(" in")

        lock_form.addRow("Duration", self.duration_spin)
        lock_form.addRow("Return period", self.rp_spin)
        lock_form.addRow("Total depth", self.depth_spin)
        left_col.addLayout(lock_form)

        # RIGHT COLUMN (other params)
        right_col = QtWidgets.QFormLayout()
        right_col.setHorizontalSpacing(10)
        right_col.setVerticalSpacing(6)
        self.dist_combo = QtWidgets.QComboBox()
        self.dist_combo.addItems(DISTRIBUTIONS)
        self.dist_combo.setCurrentText("scs_type_ii")
        self.start_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.start_date.setDisplayFormat("M/d/yyyy")
        self.start_date.setCalendarPopup(True)
        self.start_date.setKeyboardTracking(True)  # allow typing M/D/YYYY
        self.step_spin = QtWidgets.QDoubleSpinBox()
        self.step_spin.setRange(0.1, 1e4)
        self.step_spin.setValue(5.0)
        self.step_spin.setSuffix(" min")
        self.custom_edit = QtWidgets.QLineEdit()
        self.custom_edit.setObjectName("custom_path")
        self.custom_edit.setPlaceholderText(
            "CSV [fraction/time, cumulative] if Distribution = user"
        )
        self.custom_edit.setText(self.settings.value("custom_path", ""))
        btn_custom = QtWidgets.QPushButton("Browse")
        btn_custom.clicked.connect(lambda: self._choose(self.custom_edit, save=False))
        row_custom = QtWidgets.QHBoxLayout()
        row_custom.addWidget(self.custom_edit)
        row_custom.addWidget(btn_custom)
        self.decimate_chk = QtWidgets.QCheckBox("Auto-aggregate plots when large")
        self.decimate_chk.setChecked(True)

        right_col.addRow("Distribution", self.dist_combo)
        right_col.addRow("Start date", self.start_date)
        right_col.addRow("Time step", self.step_spin)
        right_col.addRow("Custom curve", row_custom)
        right_col.addRow("", self.decimate_chk)

        params_h.addLayout(left_col, 1)
        params_h.addLayout(right_col, 1)

        # Outputs (CSV + DAT; export variable next to CSV path)
        gb_out = QtWidgets.QGroupBox("Outputs")
        fo = QtWidgets.QFormLayout(gb_out)
        self.gauge_edit = QtWidgets.QLineEdit("System")
        self.export_combo = QtWidgets.QComboBox()
        for t, v in EXPORTS:
            self.export_combo.addItem(t, v)
        self.csv_edit = QtWidgets.QLineEdit()
        self.csv_edit.setObjectName("csv_path")
        self.csv_edit.setText(self.settings.value("csv_path", ""))
        self.dat_edit = QtWidgets.QLineEdit()
        self.dat_edit.setObjectName("dat_path")
        self.dat_edit.setText(self.settings.value("dat_path", ""))
        self.pptx_edit = QtWidgets.QLineEdit()
        self.pptx_edit.setObjectName("pptx_path")
        self.pptx_edit.setText(self.settings.value("pptx_path", ""))
        btn_csv = QtWidgets.QPushButton("")
        btn_dat = QtWidgets.QPushButton("")
        btn_pptx = QtWidgets.QPushButton("")
        btn_csv.clicked.connect(
            lambda: self._choose(self.csv_edit, save=True, ext=".csv")
        )
        btn_dat.clicked.connect(
            lambda: self._choose(self.dat_edit, save=True, ext=".dat")
        )
        btn_pptx.clicked.connect(
            lambda: self._choose(self.pptx_edit, save=True, ext=".pptx")
        )

        row_csv = QtWidgets.QHBoxLayout()
        row_csv.addWidget(self.export_combo, 0)
        row_csv.addWidget(self.csv_edit, 1)
        row_csv.addWidget(btn_csv, 0)

        row_dat = QtWidgets.QHBoxLayout()
        row_dat.addWidget(self.dat_edit, 1)
        row_dat.addWidget(btn_dat, 0)

        row_pptx = QtWidgets.QHBoxLayout()
        row_pptx.addWidget(self.pptx_edit, 1)
        row_pptx.addWidget(btn_pptx, 0)

        fo.addRow("Gauge name", self.gauge_edit)
        fo.addRow("CSV", row_csv)
        fo.addRow("DAT (in/hr)", row_dat)
        fo.addRow("PPTX", row_pptx)

        # Actions / docs
        actions = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Export Files")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.export_png_btn = QtWidgets.QPushButton("Export Plot PNG")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        self.progress_label = QtWidgets.QLabel("")
        self.progress_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.progress_label.setMinimumWidth(120)
        self.progress_label.hide()
        self.docs_btn = QtWidgets.QPushButton("Help / Docs")
        actions.addWidget(self.run_btn)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.export_png_btn)
        actions.addWidget(self.progress_bar)
        actions.addWidget(self.progress_label)
        actions.addStretch(1)
        actions.addWidget(self.docs_btn)

        # Log
        self.output_box = QtWidgets.QPlainTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setMaximumHeight(110)

        # LEFT assembly
        left_v.addWidget(gb_loc)
        left_v.addWidget(self.map_group, 3)
        left_v.addWidget(gb_noaa, 1)
        left_v.addWidget(gb_params)
        left_v.addWidget(gb_out)
        left_v.addLayout(actions)
        left_v.addWidget(self.output_box)

        splitter.addWidget(left)

        # ---------- RIGHT: plots (top) + results table (bottom) ----------
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        right_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right_layout.addWidget(right_split)

        # Plots panel (top; ~2/3)
        plot_panel = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(plot_panel)
        pv.setContentsMargins(4, 4, 4, 4)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        # 3 stacked subplots: Intensity, Volume, Cumulative
        self.ax1 = self.figure.add_subplot(311)
        self.ax2 = self.figure.add_subplot(312)
        self.ax3 = self.figure.add_subplot(313)

        pv.addWidget(self.canvas, 1)
        right_split.addWidget(plot_panel)

        # Results table (bottom; ~1/3)
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(
            ["time_min", "intensity_in_hr", "volume_in", "cumulative_in", "timestamp"]
        )
        self.results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        right_split.addWidget(self.results_table)

        # Give plots ~2/3 and table ~1/3
        right_split.setStretchFactor(0, 2)
        right_split.setStretchFactor(1, 1)
        right_split.setSizes([800, 400])

        # Theme colors for matplotlib (AFTER axes exist)
        self._apply_theme_to_mpl()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([720, 1000])

        # --------- signals ----------
        self.noaa_table.cellClicked.connect(self._noaa_cell_clicked)
        self.use_noaa_chk.toggled.connect(self._update_noaa_lock)

        for w in (self.duration_spin, self.step_spin, self.depth_spin):
            w.valueChanged.connect(self._redraw)
        self.rp_spin.valueChanged.connect(self._interp_depth_from_rp)
        self.duration_spin.valueChanged.connect(self._interp_rp_from_duration_depth)
        self.depth_spin.valueChanged.connect(self._interp_rp_from_duration_depth)

        self.dist_combo.currentIndexChanged.connect(self._distribution_changed)
        self.export_combo.currentIndexChanged.connect(self._redraw)
        self.custom_edit.textChanged.connect(self._redraw)

        self.lat_edit.textChanged.connect(self._debounced_noaa)
        self.lon_edit.textChanged.connect(self._debounced_noaa)

        self.export_png_btn.clicked.connect(self._save_png)
        self.run_btn.clicked.connect(self._run_cli)
        self.cancel_btn.clicked.connect(self._cancel_cli)
        self.docs_btn.clicked.connect(self._show_docs)

        # NOAA fetch debouncer
        self._noaa_timer = QtCore.QTimer(self)
        self._noaa_timer.setSingleShot(True)
        self._noaa_timer.setInterval(400)
        self._noaa_timer.timeout.connect(self._load_noaa)

        # Init
        app = QtWidgets.QApplication.instance()
        if app:
            apply_dark_palette(app)
        self._load_noaa()
        self._update_noaa_lock()
        self._redraw()

    # ---------- theme ----------
    def _apply_theme_to_mpl(self):
        pal = QtWidgets.QApplication.palette()
        bg = pal.window().color()

        def rgb(c):
            return (c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)

        white = (1.0, 1.0, 1.0)

        self.figure.set_facecolor(rgb(bg))
        for ax in (self.ax1, self.ax2, self.ax3):
            ax.set_facecolor(rgb(bg))
            # force white titles + axis labels + ticks
            ax.title.set_color(white)
            ax.xaxis.label.set_color(white)
            ax.yaxis.label.set_color(white)
            ax.tick_params(colors=white)
            for sp in ax.spines.values():
                sp.set_color(white)

        # bars follow highlight color; lines can be white as well
        accent = pal.highlight().color()
        self._bar_color = rgb(accent)
        self._line_color = white

    # ---------- helpers ----------
    def _choose(self, edit: QtWidgets.QLineEdit, save: bool = False, ext: str = ""):
        start = self.settings.value(
            edit.objectName(), self.settings.value("last_dir", "")
        )
        if save:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save As", start, filter="*" + ext if ext else "*"
            )
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open", start)
        if path:
            if ext and not Path(path).suffix:
                path = str(Path(path).with_suffix(ext))
            edit.setText(path)
            self.settings.setValue(edit.objectName(), path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _start_busy(self, msg: str):
        self._busy_count += 1
        self.progress_label.setText(msg)
        if self._busy_count == 1:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            self.progress_label.show()
            QtWidgets.QApplication.processEvents()

    def _stop_busy(self):
        if self._busy_count > 0:
            self._busy_count -= 1
        if self._busy_count == 0:
            self.progress_bar.hide()
            self.progress_label.hide()
            self.progress_bar.setRange(0, 1)

    def _geocode_address(self) -> None:
        addr = self.addr_edit.text().strip()
        if not addr:
            return
        if _GEOCODER is None:
            QtWidgets.QMessageBox.warning(
                self, "Geocoding unavailable", "geopy is not installed."
            )
            return
        try:
            loc = _GEOCODER.geocode(addr)
        except Exception:
            loc = None
        if not loc:
            QtWidgets.QMessageBox.warning(
                self, "Geocoding error", "Location not found."
            )
            return
        self.lat_edit.setText(f"{loc.latitude:.4f}")
        self.lon_edit.setText(f"{loc.longitude:.4f}")

    def _debounced_noaa(self):
        self._noaa_timer.start()

    def _load_noaa(self):
        try:
            lat = float(self.lat_edit.text().strip())
            lon = float(self.lon_edit.text().strip())
        except Exception:
            return
        self.noaa_table.clear()
        self.noaa_table.setRowCount(0)
        self.noaa_table.setColumnCount(0)
        self.output_box.appendPlainText("Fetching NOAA table")
        self._start_busy("Fetching NOAA table")
        self._noaa_thread = NOAAThread(lat, lon)
        self._noaa_thread.table.connect(self._apply_noaa_table)
        self._noaa_thread.start()

    def _apply_noaa_table(self, df):
        self._stop_busy()
        self._df_noaa = df
        if df is None or df.empty:
            self.noaa_table.setRowCount(0)
            self.noaa_table.setColumnCount(0)
            self.output_box.appendPlainText("NOAA table unavailable.")
            return
        rows, cols = list(df.index), list(df.columns)
        self.noaa_table.setRowCount(len(rows))
        self.noaa_table.setColumnCount(len(cols))
        self.noaa_table.setHorizontalHeaderLabels([str(c) for c in cols])
        self.noaa_table.setVerticalHeaderLabels([str(r) for r in rows])
        for r, idx in enumerate(rows):
            for c, col in enumerate(cols):
                val = df.loc[idx, col]
                it = QtWidgets.QTableWidgetItem(f"{float(val):.3f}")
                it.setTextAlignment(QtCore.Qt.AlignCenter)
                self.noaa_table.setItem(r, c, it)
        self.noaa_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.noaa_table.resizeRowsToContents()
        self.output_box.appendPlainText("NOAA table ready. Click a cell to apply.")

    def _update_noaa_lock(self):
        locked = self.use_noaa_chk.isChecked()
        # Instead of disabling the widgets (which blends into the dark theme),
        # make them read-only and style them so the locked state is obvious.
        for w in (self.duration_spin, self.rp_spin, self.depth_spin):
            w.setReadOnly(locked)
            w.setButtonSymbols(
                QtWidgets.QAbstractSpinBox.NoButtons
                if locked
                else QtWidgets.QAbstractSpinBox.UpDownArrows
            )
            if locked:
                w.setStyleSheet("QDoubleSpinBox { background: #2d2d2d; color: #888; }")
            else:
                w.setStyleSheet("")
        # Values remain until user clicks a NOAA cell

    def _nearest_row_series(self, duration_hr: float):
        if self._df_noaa is None or self._df_noaa.empty:
            return None, None
        mins_target = duration_hr * 60.0
        mins = np.array(
            [_label_to_minutes(str(idx)) for idx in self._df_noaa.index], dtype=float
        )
        if not len(mins):
            return None, None
        i = int(np.nanargmin(np.abs(mins - mins_target)))
        label = list(self._df_noaa.index)[i]
        return self._df_noaa.iloc[i], label

    def _interp_depth_from_rp(self):
        if self.use_noaa_chk.isChecked() or self._in_interp:
            return
        if self._df_noaa is None or self._df_noaa.empty:
            return
        self._in_interp = True
        try:
            s, _ = self._nearest_row_series(self.duration_spin.value())
            if s is None:
                return
            xs = np.array([float(c) for c in s.index], dtype=float)  # ARIs
            ys = s.values.astype(float)  # depths
            rp = float(self.rp_spin.value())
            depth = float(np.interp(rp, xs, ys, left=ys[0], right=ys[-1]))
            self.depth_spin.setValue(round(depth, 3))
        finally:
            self._in_interp = False
        self._redraw()

    def _interp_rp_from_duration_depth(self):
        if self.use_noaa_chk.isChecked() or self._in_interp:
            return
        if self._df_noaa is None or self._df_noaa.empty:
            return
        self._in_interp = True
        try:
            s, _ = self._nearest_row_series(self.duration_spin.value())
            if s is None:
                return
            xs = s.values.astype(float)  # depths
            ys = np.array([float(c) for c in s.index], dtype=float)  # ARIs
            depth = float(self.depth_spin.value())
            order = np.argsort(xs)
            xs_sorted = xs[order]
            ys_sorted = ys[order]
            rp = float(
                np.interp(
                    depth, xs_sorted, ys_sorted, left=ys_sorted[0], right=ys_sorted[-1]
                )
            )
            self.rp_spin.setValue(round(rp, 3))
        finally:
            self._in_interp = False
        self._redraw()

    def _noaa_cell_clicked(self, r: int, c: int):
        if self._df_noaa is None:
            return
        try:
            rp = int(float(list(self._df_noaa.columns)[c]))
            depth = float(self._df_noaa.iloc[r, c])
            label = list(self._df_noaa.index)[r]
        except Exception:
            return
        self.rp_spin.setValue(rp)
        self.depth_spin.setValue(depth)
        minutes = _label_to_minutes(label)
        if not math.isfinite(minutes):
            minutes = self.duration_spin.value() * 60.0
        self.duration_spin.setValue(round(minutes / 60.0, 6))
        # keep bins reasonable
        dur_hr = self.duration_spin.value()
        n_bins = (dur_hr * 60.0) / max(self.step_spin.value(), 1e-9)
        if n_bins > TARGET_MAX_BINS:
            new_step = math.ceil((dur_hr * 60.0) / TARGET_MAX_BINS)
            if new_step > self.step_spin.value():
                self.step_spin.setValue(new_step)
                self.output_box.appendPlainText(
                    f"Large storm: auto-increased time step to {new_step} min to keep bins  {TARGET_MAX_BINS}."
                )
        self._redraw()

    def _distribution_changed(self):
        new_dist = self.dist_combo.currentText()
        if new_dist == "user" and not self.custom_edit.text().strip():
            start = self.settings.value(
                "custom_path", self.settings.value("last_dir", "")
            )
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Select custom distribution CSV",
                start,
                filter="CSV Files (*.csv);;All Files (*)",
            )
            if path:
                self.custom_edit.setText(path)
                self.settings.setValue("custom_path", path)
                self.settings.setValue("last_dir", str(Path(path).parent))
            else:
                self.dist_combo.blockSignals(True)
                self.dist_combo.setCurrentText(self._last_dist)
                self.dist_combo.blockSignals(False)
                return
        self._last_dist = new_dist
        self._redraw()

    def _save_png(self):
        start = self.settings.value("last_dir", "")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Plot PNG",
            start,
            filter="PNG Files (*.png)",
        )
        if path:
            self.settings.setValue("last_dir", str(Path(path).parent))
            self.figure.savefig(path)

    def _append_proc(self, data: QtCore.QByteArray):
        s = bytes(data).decode("utf-8", "ignore").rstrip()
        if s:
            self.output_box.appendPlainText(s)

    def _on_finished(self, code: int):
        self._stop_busy()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.output_box.appendPlainText(f"Finished with code {code}")

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("custom_path", self.custom_edit.text())
        self.settings.setValue("csv_path", self.csv_edit.text())
        self.settings.setValue("dat_path", self.dat_edit.text())
        self.settings.setValue("pptx_path", self.pptx_edit.text())
        super().closeEvent(event)

    # ---- plotting + results table ----
    def _aggregate_bars(self, df, step_min: float, max_bars: int):
        n = len(df)
        if n <= max_bars:
            widths = np.full(n, step_min, dtype=float)
            return (
                df["time_min"].to_numpy(),
                df["intensity_in_hr"].to_numpy(),
                df["volume_in"].to_numpy(),
                df["cumulative_in"].to_numpy(),
                widths,
            )
        k = int(math.ceil(n / max_bars))
        starts = np.arange(0, n, k)
        counts = np.diff(np.append(starts, n))
        t = df["time_min"].to_numpy()[starts]
        vol = np.add.reduceat(df["volume_in"].to_numpy(), starts)
        cum = df["cumulative_in"].to_numpy()[np.clip(starts + counts - 1, 0, n - 1)]
        widths = counts * step_min
        inten = vol / (widths / 60.0)
        return t, inten, vol, cum, widths

    def _update_results_table(self, df):
        cols = [
            "Timestep (min)",
            "Intensity (in/hr)",
            "Volume (in)",
            "Cumulative (in)",
            "Datetime",
        ]
        show_ts = "timestamp" in df.columns
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(cols)
        self.results_table.setRowCount(len(df))
        for r in range(len(df)):
            self.results_table.setItem(
                r, 0, QtWidgets.QTableWidgetItem(f"{df.iloc[r]['time_min']:.2f}")
            )
            self.results_table.setItem(
                r, 1, QtWidgets.QTableWidgetItem(f"{df.iloc[r]['intensity_in_hr']:.3f}")
            )
            self.results_table.setItem(
                r, 2, QtWidgets.QTableWidgetItem(f"{df.iloc[r]['volume_in']:.3f}")
            )
            self.results_table.setItem(
                r, 3, QtWidgets.QTableWidgetItem(f"{df.iloc[r]['cumulative_in']:.3f}")
            )
            ts = df.iloc[r]["timestamp"] if show_ts else None
            if ts:
                try:
                    ts = ts.to_pydatetime()
                except Exception:
                    pass
                ts_str = f"{ts.month}-{ts.day}-{ts.year} {ts.hour}:{ts.minute:02d}"
            else:
                ts_str = ""
            self.results_table.setItem(r, 4, QtWidgets.QTableWidgetItem(ts_str))
        self.results_table.resizeRowsToContents()

    def _redraw(self):
        depth = self.depth_spin.value()
        if depth <= 0:
            return

        self._start_busy("Building storm")
        try:
            dist = self.dist_combo.currentText()
            custom_path = None
            if dist == "user":
                p = self.custom_edit.text().strip()
                if not p:
                    self.output_box.appendPlainText(
                        "Select a custom CSV to plot 'user' distribution."
                    )
                    return
                custom_path = Path(p)

            # start datetime (date only, midnight)
            start_dt = QtCore.QDateTime(self.start_date.date()).toPyDateTime()

            df = build_storm(
                depth=depth,
                duration_hr=self.duration_spin.value(),
                timestep_min=self.step_spin.value(),
                distribution=dist,
                peak=None,
                custom_curve_path=custom_path,
                start=start_dt,
            )
            self._current_df = df
            self._update_results_table(df)
        finally:
            self._stop_busy()

        # Aggregate for plotting
        t_min, inten, vol, cum, widths_min = self._aggregate_bars(
            df,
            self.step_spin.value(),
            MAX_PLOT_BARS if self.decimate_chk.isChecked() else 10**9,
        )

        # Convert to hours for plotting
        t_hr = np.asarray(t_min, dtype=float) / 60.0
        widths_hr = np.asarray(widths_min, dtype=float) / 60.0

        # Ax1: Intensity
        self.ax1.clear()
        self.ax1.bar(t_hr, inten, width=widths_hr, color=self._bar_color)
        self.ax1.set_ylabel("Intensity (in/hr)")
        self.ax1.set_title("Hyetograph (Intensity)")
        self.ax1.set_xlabel("Time (hr)")

        # Ax2: Volume (incremental depth)
        self.ax2.clear()
        self.ax2.bar(t_hr, vol, width=widths_hr, color=self._bar_color)
        self.ax2.set_ylabel("Volume (in)")
        self.ax2.set_title("Incremental Volume")
        self.ax2.set_xlabel("Time (hr)")

        # Ax3: Cumulative mass curve
        self.ax3.clear()
        self.ax3.plot(t_hr, cum, color=self._line_color, rasterized=True)
        self.ax3.set_ylabel("Cumulative Depth (in)")
        self.ax3.set_title("Cumulative Mass Curve")
        self.ax3.set_xlabel("Time (hr)")

        # ensure titles and axis labels match the theme
        self._apply_theme_to_mpl()

        self.figure.tight_layout()
        self.canvas.draw()

    def _run_cli(self):
        args = [
            "-m",
            "hh_tools.design_storm" if __package__ else "design_storm",
            "--duration",
            str(self.duration_spin.value()),
            "--time-step",
            str(self.step_spin.value()),
            "--distribution",
            self.dist_combo.currentText(),
            "--start-datetime",
            QtCore.QDateTime(self.start_date.date()).toString(QtCore.Qt.ISODate),
            "--gauge-name",
            self.gauge_edit.text(),
            "--export-type",
            self.export_combo.currentData(),
        ]
        lat, lon = self.lat_edit.text().strip(), self.lon_edit.text().strip()
        if lat and lon:
            args += ["--location", f"{lat},{lon}"]
            # Whether we lock or not, the CLI depth selection is controlled below
            if self.use_noaa_chk.isChecked():
                args += ["--use-noaa"]
        if self.depth_spin.value() > 0 and not self.use_noaa_chk.isChecked():
            args += ["--depth", str(self.depth_spin.value())]
        args += ["--return-period", str(self.rp_spin.value())]
        if self.csv_edit.text():
            args += ["--out-csv", self.csv_edit.text()]
        if self.dat_edit.text():
            args += ["--out-dat", self.dat_edit.text()]
        if self.pptx_edit.text():
            args += ["--pptx", self.pptx_edit.text()]
        self.output_box.appendPlainText("Running: python " + " ".join(args))
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._start_busy("Processing")
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(
            lambda: self._append_proc(self.process.readAllStandardOutput())
        )
        self.process.readyReadStandardError.connect(
            lambda: self._append_proc(self.process.readAllStandardError())
        )
        self.process.finished.connect(lambda code, _s: self._on_finished(code))
        self.process.start(sys.executable, args)

    def _cancel_cli(self):
        if getattr(self, "process", None) and self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self._stop_busy()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _show_docs(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Design Storm - Help / Documentation")
        dlg.resize(760, 560)
        lay = QtWidgets.QVBoxLayout(dlg)
        txt = QtWidgets.QTextBrowser()
        txt.setOpenExternalLinks(True)
        txt.setHtml(
            """
        <h2>Design Storm Generator</h2>
        <p><b>Purpose.</b> Build synthetic hyetographs from NOAA Atlas 14 depths and temporal patterns (Beta(,) presets).
        Optionally, supply a custom cumulative curve (CSV).</p>
        <h3>Workflow</h3>
        <ol>
          <li>Pick a location on the map (NOAA table refreshes automatically).</li>
          <li>Click a cell in the NOAA table to set <i>Return period</i>, <i>Depth</i>, and <i>Duration</i>.</li>
          <li>Choose a distribution (SCS Types or Huff quartiles; Beta approximations).</li>
          <li>Export CSV / DAT (DAT always in in/hr).</li>
        </ol>
        <h3>Interpolation</h3>
        <p>When <i>Use NOAA selection</i> is <b>unchecked</b>:
        editing <i>Return period</i> will interpolate <i>Depth</i> along the selected duration row.
        Editing <i>Duration</i> or <i>Total depth</i> updates <i>Return period</i> to stay consistent.</p>
        <h3>Methods</h3>
        <p>Temporal patterns use Beta(,) on [0,1] without shifting. A commented implementation for
        dimensionless proportion tables is included in <code>design_storm.py</code> if you prefer that method.</p>
        """
        )
        lay.addWidget(txt)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(dlg.reject)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec_()


def main():
    app = QtWidgets.QApplication(sys.argv)
    if _MATPLOTLIB_ERROR is not None:
        QtWidgets.QMessageBox.critical(
            None,
            "Missing dependency",
            "matplotlib is required to run the Design Storm tool.\n"
            "Please install it and try again.",
        )
        return
    apply_dark_palette(app)
    w = DesignStormWindow()
    w.resize(1420, 900)
    w.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
