"""GUI wrapper around the validate-inp command line tool.

This version provides drag-and-drop support for selecting multiple INP files
and displays validation results in a live table.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class FileListWidget(QtWidgets.QListWidget):
    """List widget that accepts dropped file paths."""

    def __init__(self) -> None:  # pragma: no cover - GUI behaviour
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)

    def dragEnterEvent(
        self, event: QtGui.QDragEnterEvent
    ) -> None:  # pragma: no cover - GUI only
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(
        self, event: QtGui.QDragMoveEvent
    ) -> None:  # pragma: no cover - GUI only
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # pragma: no cover - GUI only
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            self.add_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def add_paths(self, paths: Iterable[str]) -> None:
        for path in paths:
            if path and not self._contains(path):
                self.addItem(path)

    def _contains(self, path: str) -> bool:
        for i in range(self.count()):
            if self.item(i).text() == path:
                return True
        return False


class ValidateInpWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Validate INP")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "validate_inp.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        form = QtWidgets.QFormLayout(self)

        # ------------------------------------------------------------------
        # File selection with drag & drop support
        # ------------------------------------------------------------------
        self.files_list = FileListWidget()
        self.files_list.setToolTip("Drag and drop INP files here or use Add")
        # Backwards compatibility: older code expected a QLineEdit called
        # ``files_edit`` with a ``setText`` method.  Expose the list widget
        # under that name and provide a compatible setter.
        self.files_edit = self.files_list
        self.files_list.setText = lambda path: self.files_list.add_paths([path])
        saved = self.settings.value("files", "")
        if saved:
            self.files_list.add_paths(saved.split(";"))
        add_btn = QtWidgets.QPushButton("Add")
        add_btn.clicked.connect(self._choose_files)
        remove_btn = QtWidgets.QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_selected)
        files_widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(files_widget)
        vbox.addWidget(self.files_list)
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(add_btn)
        hbox.addWidget(remove_btn)
        vbox.addLayout(hbox)
        form.addRow("Files", files_widget)

        # Options
        self.range_check = QtWidgets.QCheckBox("Check numeric ranges", checked=True)
        form.addRow(self.range_check)
        self.ref_check = QtWidgets.QCheckBox("Check cross references", checked=True)
        form.addRow(self.ref_check)

        # Run button
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("validate_inp", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        form.addRow(btn_row)

        # Results table
        self.results = QtWidgets.QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["File", "Errors", "Warnings", "Status"])
        self.results.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self.results.itemDoubleClicked.connect(self._show_details)
        form.addRow(self.results)

        # QProcess for running validations sequentially
        self.process = QtCore.QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self._queue: List[Tuple[str, int]] = []  # (path, row)

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------
    def _choose_files(self) -> None:
        start = self.settings.value("last_dir", "")
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select INP files", start
        )
        if paths:
            self.files_list.add_paths(paths)
            self.settings.setValue("last_dir", str(Path(paths[0]).parent))

    def _remove_selected(self) -> None:
        for item in self.files_list.selectedItems():
            self.files_list.takeItem(self.files_list.row(item))

    # ------------------------------------------------------------------
    # Running validations
    # ------------------------------------------------------------------
    def _run(self) -> None:
        paths = [self.files_list.item(i).text() for i in range(self.files_list.count())]
        if not paths:
            QtWidgets.QMessageBox.warning(
                self, "No files", "Please select at least one file."
            )
            return
        self.results.setRowCount(0)
        self._queue = []
        for path in paths:
            row = self.results.rowCount()
            self.results.insertRow(row)
            self.results.setItem(row, 0, QtWidgets.QTableWidgetItem(path))
            self.results.setItem(row, 1, QtWidgets.QTableWidgetItem(""))
            self.results.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
            self.results.setItem(row, 3, QtWidgets.QTableWidgetItem("Pending"))
            self._queue.append((path, row))
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._start_next()

    def _start_next(self) -> None:
        if not self._queue:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return
        path, row = self._queue.pop(0)
        self._current_row = row
        args = [path]
        if not self.range_check.isChecked():
            args.append("--no-range")
        if not self.ref_check.isChecked():
            args.append("--no-crossref")
        args.append("--json")
        self.process.start(sys.executable, ["-m", "hh_tools.validate_inp", *args])

    def _finished(self, _code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="ignore"
        )
        try:
            report = json.loads(data)[0]
        except Exception:  # pragma: no cover - unexpected output
            report = {"file": "", "errors": [], "warnings": []}
        errors = report.get("errors", [])
        warnings = report.get("warnings", [])
        item = self.results.item(self._current_row, 0)
        item.setData(QtCore.Qt.UserRole, report)
        self.results.setItem(
            self._current_row, 1, QtWidgets.QTableWidgetItem(str(len(errors)))
        )
        self.results.setItem(
            self._current_row, 2, QtWidgets.QTableWidgetItem(str(len(warnings)))
        )
        status = "OK" if not errors and not warnings else "Issues"
        self.results.setItem(self._current_row, 3, QtWidgets.QTableWidgetItem(status))
        self._start_next()

    def _cancel(self) -> None:
        self._queue.clear()
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            if hasattr(self, "_current_row"):
                self.results.setItem(
                    self._current_row,
                    3,
                    QtWidgets.QTableWidgetItem("Canceled"),
                )
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _show_details(
        self, item: QtWidgets.QTableWidgetItem
    ) -> None:  # pragma: no cover - GUI only
        row = item.row()
        rep = self.results.item(row, 0).data(QtCore.Qt.UserRole)
        if not rep:
            return
        lines = []
        for issue in rep.get("errors", []):
            lines.append(f"{issue['line']}: ERROR: {issue['message']}")
        for issue in rep.get("warnings", []):
            lines.append(f"{issue['line']}: WARNING: {issue['message']}")
        if not lines:
            lines = ["OK"]
        QtWidgets.QMessageBox.information(
            self, rep.get("file", "Details"), "\n".join(lines)
        )

    def _error(
        self, err: QtCore.QProcess.ProcessError
    ) -> None:  # pragma: no cover - GUI only
        messages = {
            QtCore.QProcess.ProcessError.FailedToStart: (
                "Failed to start validator. Ensure Python is installed and on the PATH."
            ),
            QtCore.QProcess.ProcessError.Crashed: "validate-inp crashed.",
        }
        QtWidgets.QMessageBox.critical(
            self, "Process error", messages.get(err, str(err))
        )
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        paths = [self.files_list.item(i).text() for i in range(self.files_list.count())]
        self.settings.setValue("files", ";".join(paths))
        super().closeEvent(event)


def main() -> None:  # pragma: no cover - GUI only
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = ValidateInpWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":  # pragma: no cover - GUI only
    main()
