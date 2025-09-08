"""GUI wrapper around the summarize-outfiles command line tool."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


class SummarizeOutfilesWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Summarize Out Files")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "summarize_outfiles.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        form = QtWidgets.QFormLayout(self)

        # Outfiles selection
        self.files_edit = QtWidgets.QLineEdit()
        self.files_edit.setObjectName("files")
        self.files_edit.setToolTip("Semicolon-separated .out files to summarize")
        self.files_edit.setText(self.settings.value("files", ""))
        browse = QtWidgets.QPushButton("Browse")
        browse.setToolTip("Browse for .out files")
        browse.clicked.connect(self._choose_files)
        files_layout = QtWidgets.QHBoxLayout()
        files_layout.addWidget(self.files_edit)
        files_layout.addWidget(browse)
        form.addRow("Out files", files_layout)

        # Type
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["node", "link", "subcatchment", "system"])
        self.type_combo.setToolTip("Object type to summarize")
        form.addRow("Type", self.type_combo)

        # IDs and params
        self.ids_edit = QtWidgets.QLineEdit()
        self.ids_edit.setToolTip("Comma-separated IDs to include")
        form.addRow("IDs", self.ids_edit)
        self.params_edit = QtWidgets.QLineEdit("Flow_rate")
        self.params_edit.setToolTip("Comma-separated parameters to summarize")
        form.addRow("Params", self.params_edit)

        # Output path
        self.output_edit = QtWidgets.QLineEdit(
            self.settings.value("output_path", "summary_report.csv")
        )
        self.output_edit.setObjectName("output_path")
        self.output_edit.setToolTip("Path for output CSV report")
        browse_out = QtWidgets.QPushButton("Browse")
        browse_out.setToolTip("Choose output CSV path")
        browse_out.clicked.connect(self._choose_output)
        out_layout = QtWidgets.QHBoxLayout()
        out_layout.addWidget(self.output_edit)
        out_layout.addWidget(browse_out)
        form.addRow("Output", out_layout)

        # Run/Cancel buttons
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.setToolTip("Run summarization")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("Cancel running summarization")
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("summarize_outfiles", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        form.addRow(btn_row)

        # Progress indicator
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setToolTip("Shows progress while summarizing")
        form.addRow(self.progress)

        # Output display
        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        self.output_box.setToolTip("Displays output from summarization")
        form.addRow(self.output_box)

        # Subprocess handling
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

    # ------------------------------------------------------------------
    def _choose_files(self) -> None:
        start = self.settings.value("files", self.settings.value("last_dir", ""))
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select .out files", start
        )
        if paths:
            self.files_edit.setText(";".join(paths))
            self.settings.setValue("files", ";".join(paths))
            self.settings.setValue("last_dir", str(Path(paths[0]).parent))

    def _choose_output(self) -> None:
        start = self.settings.value("output_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select output CSV", start
        )
        if path:
            self.output_edit.setText(path)
            self.settings.setValue("output_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _run(self) -> None:
        files_text = self.files_edit.text().strip()
        if not files_text:
            QtWidgets.QMessageBox.warning(
                self, "Missing files", "Please choose at least one file."
            )
            return
        files = [f.strip() for f in files_text.split(";") if f.strip()]
        args: list[str] = [*files, "--type", self.type_combo.currentText()]
        ids = self.ids_edit.text().strip()
        if ids:
            args.extend(["--ids", ids])
        params = self.params_edit.text().strip()
        if params:
            args.extend(["--params", params])
        output = self.output_edit.text().strip()
        if output:
            args.extend(["--output", output])
        self.output_box.appendPlainText(
            "Running: summarize-outfiles " + " ".join(shlex.quote(a) for a in args)
        )
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.process.start("summarize-outfiles", args)

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
        self.output_box.appendPlainText(f"Finished with code {code}\n")
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
        self.settings.setValue("files", self.files_edit.text())
        self.settings.setValue("ids", self.ids_edit.text())
        self.settings.setValue("params", self.params_edit.text())
        self.settings.setValue("output_path", self.output_edit.text())
        super().closeEvent(event)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = SummarizeOutfilesWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
