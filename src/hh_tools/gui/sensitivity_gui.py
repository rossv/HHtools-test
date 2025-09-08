"""Minimal PyQt5 front-end for :mod:`hh_tools.sensitivity`.

The GUI collects basic arguments and then invokes the ``sensitivity-analyzer``
command-line entry point.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class SensitivityWindow(QtWidgets.QWidget):
    """Collect inputs for the sensitivity analysis tool."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Sensitivity Analyzer")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "sensitivity.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        form = QtWidgets.QFormLayout(self)

        # Base INP file
        self.inp_edit = QtWidgets.QLineEdit()
        self.inp_edit.setObjectName("inp_path")
        self.inp_edit.setText(self.settings.value("inp_path", ""))
        browse_inp = QtWidgets.QPushButton("Browse")
        browse_inp.clicked.connect(self._choose_inp)
        inp_layout = QtWidgets.QHBoxLayout()
        inp_layout.addWidget(self.inp_edit)
        inp_layout.addWidget(browse_inp)
        form.addRow("Base .inp", inp_layout)

        # Parameter file
        self.param_edit = QtWidgets.QLineEdit()
        self.param_edit.setObjectName("param_path")
        self.param_edit.setText(self.settings.value("param_path", ""))
        browse_param = QtWidgets.QPushButton("Browse")
        browse_param.clicked.connect(self._choose_param)
        param_layout = QtWidgets.QHBoxLayout()
        param_layout.addWidget(self.param_edit)
        param_layout.addWidget(browse_param)
        form.addRow("Param file", param_layout)

        # Metrics
        self.metrics_edit = QtWidgets.QLineEdit()
        self.metrics_edit.setToolTip(
            "Comma-separated metrics, e.g. peak_flow,runoff_volume"
        )
        form.addRow("Metrics", self.metrics_edit)

        # Run/Cancel buttons
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("sensitivity", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        form.addRow(btn_row)

        # Progress bar and output
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        form.addRow(self.progress)

        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        form.addRow(self.output_box)

        # Subprocess handling
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _choose_inp(self) -> None:
        start = self.settings.value("inp_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select base .inp file", start
        )
        if path:
            self.inp_edit.setText(path)
            self.settings.setValue("inp_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _choose_param(self) -> None:
        start = self.settings.value("param_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select parameter file", start
        )
        if path:
            self.param_edit.setText(path)
            self.settings.setValue("param_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _run(self) -> None:
        inp = self.inp_edit.text().strip()
        params = self.param_edit.text().strip()
        metrics = self.metrics_edit.text().strip()
        if not inp or not params or not metrics:
            QtWidgets.QMessageBox.warning(
                self, "Missing input", "Please provide INP, param file and metrics"
            )
            return
        args = [inp, "--params", params, "--metrics", metrics]
        self.output_box.appendPlainText(
            "Running: sensitivity-analyzer " + " ".join(shlex.quote(a) for a in args)
        )
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.process.start(sys.executable, ["-m", "hh_tools.sensitivity", *args])

    def _handle_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.output_box.appendPlainText(data.rstrip())

    def _handle_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.output_box.appendPlainText(data.rstrip())

    def _process_finished(self, code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        """Handle completion of the subprocess and update the UI."""
        self.output_box.appendPlainText(f"Finished with code {code}")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("inp_path", self.inp_edit.text())
        self.settings.setValue("param_path", self.param_edit.text())
        super().closeEvent(event)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = SensitivityWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
