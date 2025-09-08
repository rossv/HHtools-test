"""PyQt5 front-end for event_extractor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class EventExtractorWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Event Extractor")
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

        # Output directory
        self.output_dir_edit = QtWidgets.QLineEdit()
        out_browse = QtWidgets.QPushButton("Browse")
        out_browse.clicked.connect(self._browse_output_dir)
        ol = QtWidgets.QHBoxLayout()
        ol.addWidget(self.output_dir_edit)
        ol.addWidget(out_browse)
        form.addRow("Output Dir", ol)

        # Threshold
        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setDecimals(6)
        self.threshold_spin.setRange(-1e9, 1e9)
        form.addRow("Threshold", self.threshold_spin)

        # Duration
        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(0, 1e9)
        self.duration_spin.setSuffix(" min")
        form.addRow("Min Duration", self.duration_spin)

        self.run_btn = QtWidgets.QPushButton("Extract")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("event_extractor", self))
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

    def _browse_output_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory"
        )
        if path:
            self.output_dir_edit.setText(path)

    def _run(self) -> None:
        path = self.file_edit.text().strip()
        if not path:
            QtWidgets.QMessageBox.warning(
                self, "Input Required", "Please choose an input file."
            )
            return
        args = [
            "-m",
            "hh_tools.event_extractor",
            path,
            "--threshold",
            str(self.threshold_spin.value()),
            "--min-duration",
            str(self.duration_spin.value()),
        ]
        outdir = self.output_dir_edit.text().strip()
        if outdir:
            args += ["--output-dir", outdir]
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
    if (ICON_DIR / "event_extractor.ico").exists():
        app.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "event_extractor.ico")))
    apply_dark_palette(app)
    win = EventExtractorWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":  # pragma: no cover
    main()
