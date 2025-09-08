"""PyQt5 front-end for resample_timeseries."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class ResampleWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Resample Timeseries")
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        layout.addLayout(form)

        # Input file
        self.file_edit = QtWidgets.QLineEdit()
        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_file)
        fl = QtWidgets.QHBoxLayout()
        fl.addWidget(self.file_edit)
        fl.addWidget(browse_btn)
        form.addRow("Input CSV", fl)

        # Output file
        self.output_edit = QtWidgets.QLineEdit()
        out_browse = QtWidgets.QPushButton("Browse")
        out_browse.clicked.connect(self._browse_output)
        ol = QtWidgets.QHBoxLayout()
        ol.addWidget(self.output_edit)
        ol.addWidget(out_browse)
        form.addRow("Output File", ol)

        # Frequency
        self.freq_edit = QtWidgets.QLineEdit()
        form.addRow("New timestep", self.freq_edit)

        # Format
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["csv", "dat", "tsf"])
        form.addRow("Format", self.format_combo)

        # Plot checkbox
        self.plot_check = QtWidgets.QCheckBox("Show plot")
        form.addRow("", self.plot_check)

        self.run_btn = QtWidgets.QPushButton("Resample")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("resample_timeseries", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        layout.addLayout(btn_row)

        self.process = QtCore.QProcess(self)
        self.process.finished.connect(self._finished)

    def _browse_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select CSV", "", "CSV Files (*.csv *.tsv);;All Files (*)"
        )
        if path:
            self.file_edit.setText(path)

    def _browse_output(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Resampled Series",
            "",
            "All Files (*.*)",
        )
        if path:
            self.output_edit.setText(path)

    def _run(self) -> None:
        path = self.file_edit.text().strip()
        if not path:
            QtWidgets.QMessageBox.warning(
                self, "Input Required", "Please choose an input file."
            )
            return
        args = [
            "-m",
            "hh_tools.resample_timeseries",
            path,
            "--freq",
            self.freq_edit.text().strip(),
            "--format",
            self.format_combo.currentText(),
        ]
        output = self.output_edit.text().strip()
        if output:
            args.extend(["--output", output])
        if self.plot_check.isChecked():
            args.append("--plot")
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.process.start(sys.executable, args)

    def _finished(self, _code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    if (ICON_DIR / "resample_timeseries.ico").exists():
        app.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "resample_timeseries.ico")))
    apply_dark_palette(app)
    win = ResampleWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":  # pragma: no cover
    main()
