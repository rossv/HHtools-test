"""Simple GUI to run SWMM inputs and show previous runtimes.

This module provides a small PyQt5 interface for adding ``.inp`` files either
through a file dialog or by drag and drop.  For each added file the GUI looks
for a ``.rpt`` file with the same base name and extracts the ``Total elapsed
time`` line if present.  The batch of inputs can then be executed using the
existing :mod:`hh_tools.batch_runner` entry point.
"""

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


def extract_prev_runtime(inp_path: Path) -> str | None:
    """Return the ``Total elapsed time`` string from a matching ``.rpt`` file.

    Parameters
    ----------
    inp_path:
        Path to a SWMM input file.  A ``.rpt`` file with the same stem will be
        searched in the same directory.
    """

    rpt = inp_path.with_suffix(".rpt")
    if not rpt.exists():
        return None
    try:
        lines = rpt.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        if "Total elapsed time:" in line:
            return line.split("Total elapsed time:", 1)[1].strip()
    return None


class DropTableWidget(QtWidgets.QTableWidget):
    """Table widget that accepts dropped files."""

    filesDropped = QtCore.pyqtSignal(list)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["INP file", "Previous runtime"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setAcceptDrops(True)

    # Drag/drop handling -------------------------------------------------
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
        paths: list[Path] = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() == ".inp":
                paths.append(p)
        if paths:
            self.filesDropped.emit(paths)
        event.acceptProposedAction()


class BatchRunnerWindow(QtWidgets.QWidget):
    """Collect ``.inp`` files and invoke ``batch-runner``."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Batch Runner")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "batch_runner.ico")))

        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        self.table = DropTableWidget()
        self.table.filesDropped.connect(self._add_paths)

        add_btn = QtWidgets.QPushButton("Add INP files")
        add_btn.clicked.connect(self._choose_files)

        remove_btn = QtWidgets.QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)

        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("batch_runner", self))
        btn_row.addWidget(self.help_btn)
        layout.addLayout(btn_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.output_box)

        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

        if files := self.settings.value("files", [], type=list):
            self._add_paths(Path(p) for p in files)

    # File handling ------------------------------------------------------
    def _choose_files(self) -> None:  # pragma: no cover - GUI only
        start = self.settings.value("last_dir", "")
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select INP files", start, "INP Files (*.inp)"
        )
        if paths:
            self._add_paths(Path(p) for p in paths)

    def _add_paths(self, paths: Iterable[Path]) -> None:
        paths = list(paths)
        existing = {
            Path(self.table.item(r, 0).text()) for r in range(self.table.rowCount())
        }
        for path in paths:
            if path in existing:
                continue
            runtime = extract_prev_runtime(path) or ""
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(path)))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(runtime))
        if paths:
            self.settings.setValue("last_dir", str(Path(paths[0]).parent))
            self._save_paths()

    def _remove_selected(self) -> None:  # pragma: no cover - GUI only
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self._save_paths()

    def _save_paths(self) -> None:
        paths = [self.table.item(r, 0).text() for r in range(self.table.rowCount())]
        self.settings.setValue("files", paths)

    # Running ------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - GUI only
        files = [self.table.item(r, 0).text() for r in range(self.table.rowCount())]
        if not files:
            QtWidgets.QMessageBox.warning(
                self, "No inputs", "Please add INP files to run."
            )
            return
        config = {"scenarios": [{"name": Path(f).stem, "inp": f} for f in files]}
        cfg_json = json.dumps(config)
        self.output_box.appendPlainText(
            "Running: batch-runner " + " ".join(Path(f).name for f in files)
        )
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        # Pass configuration via stdin
        program = sys.executable
        arguments = ["-m", "hh_tools.batch_runner", "-"]
        self.process.start(program, arguments)
        self.process.write(cfg_json.encode("utf-8"))
        self.process.closeWriteChannel()

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _handle_stdout(self) -> None:  # pragma: no cover - GUI only
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.output_box.appendPlainText(data.rstrip())

    def _handle_stderr(self) -> None:  # pragma: no cover - GUI only
        data = bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="ignore"
        )
        if data:
            self.output_box.appendPlainText(data.rstrip())

    def _process_finished(
        self, code: int, _status: QtCore.QProcess.ExitStatus
    ) -> None:  # pragma: no cover - GUI only
        self.output_box.appendPlainText(f"Finished with code {code}\n")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        self._save_paths()
        super().closeEvent(event)


def main() -> None:  # pragma: no cover - CLI entry point
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = BatchRunnerWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":  # pragma: no cover
    main()
