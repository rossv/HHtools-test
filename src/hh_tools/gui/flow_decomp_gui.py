"""PyQt5 front-end for :mod:`hh_tools.flowdecomp`.

This window provides a graphical interface to configure the sanitary flow
decomposition, execute it and view the resulting time-series plot.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5 import QtGui, QtWidgets

from hh_tools.flowdecomp import Decomposer
from hh_tools.gui.theme import apply_dark_palette

ICON_DIR = Path(__file__).with_name("icons")
DESCRIPTION = "Decompose sanitary flow into GWI, BWWF and WWF"


class FlowDecompWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Flow Decomposition")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "flow_decomp.ico")))
        self.resize(1000, 600)

        splitter = QtWidgets.QSplitter()
        self.setCentralWidget(splitter)

        left = QtWidgets.QWidget()
        splitter.addWidget(left)
        left_layout = QtWidgets.QVBoxLayout(left)

        # ------------------------------------------------------------------
        paths_group = QtWidgets.QGroupBox("Paths")
        paths_form = QtWidgets.QFormLayout(paths_group)
        self.flow_edit, flow_btn = self._file_selector(self._browse_flow)
        paths_form.addRow("Flow CSV", self._hbox(self.flow_edit, flow_btn))
        self.rain_edit, rain_btn = self._file_selector(self._browse_rain)
        paths_form.addRow("Rainfall CSV", self._hbox(self.rain_edit, rain_btn))
        self.gwi_edit, gwi_btn = self._file_selector(self._browse_gwi)
        paths_form.addRow("GWI CSV", self._hbox(self.gwi_edit, gwi_btn))
        self.outdir_edit, out_btn = self._dir_selector(self._browse_outdir)
        paths_form.addRow("Output Dir", self._hbox(self.outdir_edit, out_btn))
        left_layout.addWidget(paths_group)

        # ------------------------------------------------------------------
        params_group = QtWidgets.QGroupBox("Parameters")
        params_form = QtWidgets.QFormLayout(params_group)
        self.interval_edit = QtWidgets.QLineEdit("15min")
        params_form.addRow("Interval", self.interval_edit)
        self.tz_edit = QtWidgets.QLineEdit("UTC")
        params_form.addRow("Timezone", self.tz_edit)
        self.gwi_mode_combo = QtWidgets.QComboBox()
        self.gwi_mode_combo.addItems(["timeseries", "avg_monthly"])
        params_form.addRow("GWI Mode", self.gwi_mode_combo)
        self.gwi_avg_spin = QtWidgets.QDoubleSpinBox()
        self.gwi_avg_spin.setDecimals(6)
        self.gwi_avg_spin.setRange(-1e9, 1e9)
        params_form.addRow("GWI Avg", self.gwi_avg_spin)
        self.monthly_edit = QtWidgets.QLineEdit(",".join(["1.0"] * 12))
        params_form.addRow("Monthly Multipliers", self.monthly_edit)
        self.rtk_spin = QtWidgets.QSpinBox()
        self.rtk_spin.setRange(0, 3)
        params_form.addRow("RTK Components", self.rtk_spin)
        self.clip_check = QtWidgets.QCheckBox("Clip negative WWF")
        self.clip_check.setChecked(True)
        params_form.addRow(self.clip_check)
        left_layout.addWidget(params_group)

        # Component visibility
        vis_group = QtWidgets.QGroupBox("Plot Components")
        vis_layout = QtWidgets.QHBoxLayout(vis_group)
        self.show_flow_cb = QtWidgets.QCheckBox("Flow")
        self.show_flow_cb.setChecked(True)
        self.show_gwi_cb = QtWidgets.QCheckBox("GWI")
        self.show_gwi_cb.setChecked(True)
        self.show_bwwf_cb = QtWidgets.QCheckBox("BWWF")
        self.show_bwwf_cb.setChecked(True)
        self.show_wwf_cb = QtWidgets.QCheckBox("WWF")
        self.show_wwf_cb.setChecked(True)
        for cb in [self.show_flow_cb, self.show_gwi_cb, self.show_bwwf_cb, self.show_wwf_cb]:
            cb.stateChanged.connect(self._update_plot)
            vis_layout.addWidget(cb)
        left_layout.addWidget(vis_group)

        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        left_layout.addWidget(self.run_btn)
        left_layout.addStretch()

        # ------------------------------------------------------------------
        fig = Figure(figsize=(5, 4))
        self.canvas = FigureCanvas(fig)
        splitter.addWidget(self.canvas)
        self.ax = fig.add_subplot(111)
        splitter.setStretchFactor(1, 1)

        self.timeseries: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    def _file_selector(self, slot):
        edit = QtWidgets.QLineEdit()
        btn = QtWidgets.QPushButton("Browse")
        btn.clicked.connect(slot)
        return edit, btn

    def _dir_selector(self, slot):
        edit = QtWidgets.QLineEdit()
        btn = QtWidgets.QPushButton("Browse")
        btn.clicked.connect(slot)
        return edit, btn

    @staticmethod
    def _hbox(edit: QtWidgets.QWidget, btn: QtWidgets.QWidget) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(edit)
        l.addWidget(btn)
        return w

    def _browse_flow(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Flow CSV", "", "CSV Files (*.csv)")
        if path:
            self.flow_edit.setText(path)

    def _browse_rain(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Rainfall CSV", "", "CSV Files (*.csv)")
        if path:
            self.rain_edit.setText(path)

    def _browse_gwi(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "GWI CSV", "", "CSV Files (*.csv)")
        if path:
            self.gwi_edit.setText(path)

    def _browse_outdir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Output Directory")
        if path:
            self.outdir_edit.setText(path)

    # ------------------------------------------------------------------
    def _run(self) -> None:
        flow_path = self.flow_edit.text().strip()
        if not flow_path:
            QtWidgets.QMessageBox.warning(self, "Missing", "Flow CSV is required")
            return
        try:
            flow_df = pd.read_csv(flow_path, parse_dates=["timestamp"])
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to read flow CSV: {exc}")
            return

        rain_df = None
        if self.rain_edit.text().strip():
            try:
                rain_df = pd.read_csv(self.rain_edit.text().strip(), parse_dates=["timestamp"])
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to read rainfall CSV: {exc}")
                return

        gwi_df = None
        if self.gwi_edit.text().strip():
            try:
                gwi_df = pd.read_csv(self.gwi_edit.text().strip(), parse_dates=["timestamp"])
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to read GWI CSV: {exc}")
                return

        try:
            monthly = [float(v) for v in self.monthly_edit.text().split(",") if v.strip()]
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Monthly", "Monthly multipliers must be numbers")
            return

        gwi_avg_val = self.gwi_avg_spin.value()
        gwi_avg = None if (self.gwi_mode_combo.currentText() == "timeseries" and not gwi_avg_val) else gwi_avg_val

        dec = Decomposer(
            interval=self.interval_edit.text() or "15min",
            tz=self.tz_edit.text() or "UTC",
            gwi_mode=self.gwi_mode_combo.currentText(),
            gwi_avg=gwi_avg,
            gwi_monthly=monthly if monthly else None,
            rtk_components=self.rtk_spin.value(),
            clip_negative=self.clip_check.isChecked(),
        )

        try:
            res = dec.fit(flow_df, rain_df=rain_df, gwi_df=gwi_df)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", str(exc))
            return

        self.timeseries = res.timeseries
        if outdir := self.outdir_edit.text().strip():
            res.save(outdir)
        self._update_plot()

    # ------------------------------------------------------------------
    def _update_plot(self) -> None:
        if self.timeseries is None:
            return
        ts = self.timeseries
        self.ax.clear()
        t = pd.to_datetime(ts["timestamp"])  # ensure datetime
        if self.show_flow_cb.isChecked():
            self.ax.plot(t, ts["flow"], label="Flow")
        if self.show_gwi_cb.isChecked():
            self.ax.plot(t, ts["gwi"], label="GWI")
        if self.show_bwwf_cb.isChecked():
            self.ax.plot(t, ts["bwwf"], label="BWWF")
        if self.show_wwf_cb.isChecked():
            self.ax.plot(t, ts["wwf"], label="WWF")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Flow")
        self.ax.legend()
        self.ax.set_title("Flow Decomposition")
        self.canvas.draw()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = FlowDecompWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
