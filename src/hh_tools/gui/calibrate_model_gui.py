#!/usr/bin/env python3
"""PyQt5 front-end for :mod:`hh_tools.calibrate_model`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class CalibrateModelWindow(QtWidgets.QWidget):  # pragma: no cover - GUI
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Calibrate Model")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "calibrate_model.ico")))

        form = QtWidgets.QFormLayout(self)

        # Base INP
        self.inp_edit = QtWidgets.QLineEdit()
        inp_btn = QtWidgets.QPushButton("Browse")
        inp_btn.clicked.connect(lambda: self._choose_file(self.inp_edit))
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.inp_edit)
        hbox.addWidget(inp_btn)
        form.addRow("Base INP", hbox)

        # Bounds file
        self.bounds_edit = QtWidgets.QLineEdit()
        bounds_btn = QtWidgets.QPushButton("Browse")
        bounds_btn.clicked.connect(lambda: self._choose_file(self.bounds_edit))
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.bounds_edit)
        hbox.addWidget(bounds_btn)
        form.addRow("Bounds", hbox)

        # Observed data
        self.obs_edit = QtWidgets.QLineEdit()
        obs_btn = QtWidgets.QPushButton("Browse")
        obs_btn.clicked.connect(lambda: self._choose_file(self.obs_edit))
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.obs_edit)
        hbox.addWidget(obs_btn)
        form.addRow("Observed", hbox)

        # Metric
        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.addItems(["nse", "rmse"])
        form.addRow("Metric", self.metric_combo)

        # SWMM executable
        self.swmm_edit = QtWidgets.QLineEdit("swmm5")
        form.addRow("SWMM exe", self.swmm_edit)

        # Output
        self.out_edit = QtWidgets.QLineEdit()
        out_btn = QtWidgets.QPushButton("Browse")
        out_btn.clicked.connect(lambda: self._choose_save(self.out_edit))
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.out_edit)
        hbox.addWidget(out_btn)
        form.addRow("Output", hbox)

        # Run/Cancel buttons
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("calibrate_model", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        form.addRow(btn_row)

        # Output text
        self.log = QtWidgets.QTextEdit(readOnly=True)
        form.addRow(self.log)

        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stdout)
        self.process.finished.connect(self._finished)

    def _choose_file(self, edit: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file")
        if path:
            edit.setText(path)

    def _choose_save(self, edit: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Select file")
        if path:
            edit.setText(path)

    def _run(self) -> None:
        inp = self.inp_edit.text()
        bounds = self.bounds_edit.text()
        obs = self.obs_edit.text()
        out = self.out_edit.text()
        if not all([inp, bounds, obs, out]):
            QtWidgets.QMessageBox.warning(
                self, "Missing", "Please select all required files"
            )
            return
        args = [
            "-m",
            "hh_tools.calibrate_model",
            inp,
            "--bounds",
            bounds,
            "--observed",
            obs,
            "--metric",
            self.metric_combo.currentText(),
            "--output",
            out,
            "--swmm",
            self.swmm_edit.text(),
        ]
        self.log.clear()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.process.start(sys.executable, args)

    def _handle_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode()
        data += bytes(self.process.readAllStandardError()).decode()
        if data:
            self.log.append(data.rstrip())

    def _finished(self) -> None:
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QtWidgets.QMessageBox.information(self, "Done", "Calibration finished")

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.log.append("Canceled")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)


def main(argv=None) -> int:  # pragma: no cover - thin wrapper
    app = QtWidgets.QApplication(list(argv) if argv is not None else sys.argv)
    apply_dark_palette(app)
    win = CalibrateModelWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    return app.exec_()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
