#!/usr/bin/env python3
"""GUI wrapper around the inp-diff command line tool."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterable

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class InpDiffWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("INP Diff")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "inp_diff.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        form = QtWidgets.QFormLayout(self)

        # File 1
        self.file1_edit = QtWidgets.QLineEdit(self.settings.value("file1", ""))
        browse1 = QtWidgets.QPushButton("Browse")
        browse1.clicked.connect(lambda: self._choose_file(self.file1_edit))
        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(self.file1_edit)
        h1.addWidget(browse1)
        form.addRow("File 1", h1)

        # File 2
        self.file2_edit = QtWidgets.QLineEdit(self.settings.value("file2", ""))
        browse2 = QtWidgets.QPushButton("Browse")
        browse2.clicked.connect(lambda: self._choose_file(self.file2_edit))
        h2 = QtWidgets.QHBoxLayout()
        h2.addWidget(self.file2_edit)
        h2.addWidget(browse2)
        form.addRow("File 2", h2)

        # Run/Cancel buttons
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("inp_diff", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        form.addRow(btn_row)

        # Results table
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Section", "ID", "File 1", "File 2"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        form.addRow(self.table)

        self.process = QtCore.QProcess(self)
        self.process.finished.connect(self._finished)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _choose_file(
        self, edit: QtWidgets.QLineEdit
    ) -> None:  # pragma: no cover - GUI only
        start = self.settings.value("last_dir", "")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select INP file", start)
        if path:
            edit.setText(path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _run(self) -> None:
        file1 = self.file1_edit.text().strip()
        file2 = self.file2_edit.text().strip()
        if not file1 or not file2:
            QtWidgets.QMessageBox.warning(
                self, "Missing files", "Please select both INP files."
            )
            return
        self.settings.setValue("file1", file1)
        self.settings.setValue("file2", file2)
        self.table.setRowCount(0)
        args = ["-m", "hh_tools.inp_diff", file1, file2, "--json"]
        self.process.start(sys.executable, args)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

    def _finished(self, _code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="ignore"
        )
        try:
            diffs = json.loads(data)
        except Exception:  # pragma: no cover - unexpected output
            diffs = []
        self.table.setRowCount(len(diffs))
        for row, d in enumerate(diffs):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(d.get("section", "")))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(d.get("id", "")))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(d.get("file1") or ""))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(d.get("file2") or ""))
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)


def main(argv: Iterable[str] | None = None) -> int:  # pragma: no cover - GUI entry
    app = QtWidgets.QApplication(list(argv) if argv is not None else sys.argv)
    apply_dark_palette(app)
    win = InpDiffWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    return app.exec_()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
