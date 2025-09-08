"""GUI wrapper around the compare-hydrographs command line tool."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

import pandas as pd
from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette

from ..extract_timeseries import discover_ids

ICON_DIR = Path(__file__).with_name("icons")


class CompareHydrographsWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Compare Hydrographs")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "compare_hydrographs.ico")))

        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        main_layout = QtWidgets.QHBoxLayout(self)

        form_widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(form_widget)
        main_layout.addWidget(form_widget)

        mapping_group = QtWidgets.QGroupBox("Field Mapping")
        mapping_group.setToolTip(
            "Map columns from the observed CSV to SWMM output parameters."
        )
        mapping_layout = QtWidgets.QVBoxLayout(mapping_group)
        main_layout.addWidget(mapping_group)

        # SWMM .out file
        self.out_edit = QtWidgets.QLineEdit()
        self.out_edit.setObjectName("outfile")
        self.out_edit.setText(self.settings.value("outfile", ""))
        self.out_edit.textChanged.connect(self._load_element_ids)
        browse_out = QtWidgets.QPushButton("Browse")
        browse_out.clicked.connect(lambda: self._choose_file(self.out_edit))
        out_layout = QtWidgets.QHBoxLayout()
        out_layout.addWidget(self.out_edit)
        out_layout.addWidget(browse_out)
        form.addRow("SWMM .out", out_layout)

        # Observed CSV
        self.obs_edit = QtWidgets.QLineEdit()
        self.obs_edit.setObjectName("obsfile")
        self.obs_edit.setText(self.settings.value("obsfile", ""))
        self.obs_edit.textChanged.connect(self._load_observed_fields)
        browse_obs = QtWidgets.QPushButton("Browse")
        browse_obs.clicked.connect(lambda: self._choose_file(self.obs_edit))
        obs_layout = QtWidgets.QHBoxLayout()
        obs_layout.addWidget(self.obs_edit)
        obs_layout.addWidget(browse_obs)
        form.addRow("Observed CSV", obs_layout)

        # Time column(s)
        time_label = QtWidgets.QLabel("Time columns")
        time_label.setToolTip("Select columns that together form the timestamp.")
        self.time_list = QtWidgets.QListWidget()
        self.time_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.time_list.setToolTip(
            "Select one or more columns representing time components in the observed data."
        )
        self.time_list.itemSelectionChanged.connect(self._update_mapping_choices)
        mapping_layout.addWidget(time_label)
        mapping_layout.addWidget(self.time_list)

        self.mapping_rows_layout = QtWidgets.QVBoxLayout()
        mapping_layout.addLayout(self.mapping_rows_layout)

        # Example mapping row to illustrate expected input
        self.example_row: QtWidgets.QWidget | None = None
        self._show_example_row()

        add_map_btn = QtWidgets.QPushButton("Add mapping")
        add_map_btn.setToolTip("Add a mapping between an observed column and a SWMM parameter.")
        add_map_btn.clicked.connect(lambda: self._add_mapping_row())
        mapping_layout.addWidget(add_map_btn)

        self.all_columns: list[str] = []
        self.available_columns: list[str] = []
        self.param_options = [
            "Flow_rate",
            "Depth",
            "Head",
            "Velocity",
            "Flow_depth",
            "Pump_status",
        ]
        self.param_descriptions = {
            "Flow_rate": "Flow rate through the link",
            "Depth": "Water depth",
            "Head": "Hydraulic head",
            "Velocity": "Flow velocity in the link",
            "Flow_depth": "Depth of flow in the link",
            "Pump_status": "On/off status of pump",
        }
        self.mapping_rows: list[
            tuple[QtWidgets.QWidget, QtWidgets.QComboBox, QtWidgets.QComboBox]
        ] = []

        self.pending_runs: list[list[str]] = []

        self._load_observed_fields()

        # Element ID
        self.id_combo = QtWidgets.QComboBox()
        self.id_combo.setEditable(True)
        self.id_combo.setObjectName("element_id")
        self.id_combo.setEditText(self.settings.value("element_id", ""))
        form.addRow("Element ID", self.id_combo)
        self._load_element_ids()

        # Plot path
        self.plot_edit = QtWidgets.QLineEdit()
        self.plot_edit.setObjectName("plot_path")
        self.plot_edit.setText(self.settings.value("plot_path", ""))
        browse_plot = QtWidgets.QPushButton("Save As")
        browse_plot.clicked.connect(self._choose_plot)
        plot_layout = QtWidgets.QHBoxLayout()
        plot_layout.addWidget(self.plot_edit)
        plot_layout.addWidget(browse_plot)
        form.addRow("Plot Path", plot_layout)

        # PPTX path
        self.pptx_edit = QtWidgets.QLineEdit()
        self.pptx_edit.setObjectName("pptx_path")
        self.pptx_edit.setText(self.settings.value("pptx_path", ""))
        browse_pptx = QtWidgets.QPushButton("Save As")
        browse_pptx.clicked.connect(self._choose_pptx)
        pptx_layout = QtWidgets.QHBoxLayout()
        pptx_layout.addWidget(self.pptx_edit)
        pptx_layout.addWidget(browse_pptx)
        form.addRow("PPTX Path", pptx_layout)

        # Run/cancel buttons
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        help_btn = QtWidgets.QPushButton("Help")
        help_btn.clicked.connect(self._show_help)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(help_btn)
        form.addRow(btn_row)

        # Progress indicator
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        form.addRow(self.progress)

        # Output display
        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        form.addRow(self.output_box)

        # Subprocess handling
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)

    def _choose_file(self, target: QtWidgets.QLineEdit) -> None:
        start = self.settings.value(
            target.objectName(), self.settings.value("last_dir", "")
        )
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file", start)
        if path:
            target.setText(path)
            self.settings.setValue(target.objectName(), path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _choose_plot(self) -> None:
        start = self.settings.value("plot_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save plot",
            start,
            filter="PNG Files (*.png);;All Files (*)",
        )
        if path:
            self.plot_edit.setText(path)
            self.settings.setValue("plot_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _choose_pptx(self) -> None:
        start = self.settings.value("pptx_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save PowerPoint",
            start,
            filter="PowerPoint Files (*.pptx);;All Files (*)",
        )
        if path:
            self.pptx_edit.setText(path)
            self.settings.setValue("pptx_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _show_help(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Compare Hydrographs Help",
            (
                "Select a SWMM .out file and an observed CSV. "
                "Use the Field Mapping section to match observed columns "
                "to SWMM output parameters, then choose an element ID and "
                "where to save the plot."
            ),
        )

    def _load_element_ids(self) -> None:
        path = self.out_edit.text().strip()
        current = self.id_combo.currentText().strip()
        self.id_combo.blockSignals(True)
        self.id_combo.clear()
        if path and Path(path).exists():
            try:
                ids = discover_ids(path, "link")
            except Exception:
                ids = []
            if ids:
                self.id_combo.addItems(ids)
        if current:
            self.id_combo.setEditText(current)
        self.id_combo.blockSignals(False)

    def _load_observed_fields(self) -> None:
        path = self.obs_edit.text().strip()
        if not path or not Path(path).exists():
            return
        try:
            df = pd.read_csv(path, nrows=5)
        except Exception:
            return
        cols = list(df.columns)
        self.all_columns = cols
        self.time_list.blockSignals(True)
        self.time_list.clear()
        self.time_list.addItems(cols)
        keywords = ["time", "date", "year", "month", "day", "hour", "minute", "second"]
        guessed = [c for c in cols if any(k in c.lower() for k in keywords)]
        if not guessed and cols:
            guessed = [cols[0]]
        for g in guessed:
            for item in self.time_list.findItems(g, QtCore.Qt.MatchExactly):
                item.setSelected(True)
        self.time_list.blockSignals(False)

        self._update_mapping_choices()

        for row, _c, _p in self.mapping_rows:
            row.setParent(None)
            row.deleteLater()
        self.mapping_rows.clear()
        self._show_example_row()

        numeric = []
        for c in self.available_columns:
            try:
                if pd.api.types.is_numeric_dtype(df[c]):
                    numeric.append(c)
            except Exception:
                continue
        for c in numeric:
            param = "Flow_rate"
            lc = c.lower()
            if "depth" in lc:
                param = "Depth"
            elif "head" in lc:
                param = "Head"
            elif "vel" in lc:
                param = "Velocity"
            elif "flow" in lc:
                param = "Flow_rate"
            self._add_mapping_row(c, param)

    def _update_mapping_choices(self) -> None:
        selected = {item.text().strip() for item in self.time_list.selectedItems()}
        self.available_columns = [c for c in self.all_columns if c not in selected]
        for row, col_combo, _param in list(self.mapping_rows):
            cur = col_combo.currentText()
            if cur not in self.available_columns:
                self._remove_mapping_row(row)
                continue
            col_combo.blockSignals(True)
            col_combo.clear()
            col_combo.addItems(self.available_columns)
            col_combo.setCurrentText(cur)
            col_combo.blockSignals(False)

    def _hide_example_row(self) -> None:
        if self.example_row is not None:
            self.example_row.hide()

    def _show_example_row(self) -> None:
        if self.example_row is None:
            self.example_row = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(self.example_row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QtWidgets.QLabel("flow_obs"))
            layout.addWidget(QtWidgets.QLabel("Flow_rate"))
            self.example_row.setDisabled(True)
            self.mapping_rows_layout.addWidget(self.example_row)
        else:
            self.example_row.show()

    def _add_mapping_row(
        self, column: str | None = None, param: str | None = None
    ) -> None:
        if not self.available_columns:
            return
        self._hide_example_row()
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        col_combo = QtWidgets.QComboBox()
        col_combo.addItems(self.available_columns)
        col_combo.setToolTip("Observed CSV column with data to compare")
        if column:
            col_combo.setCurrentText(column)
        param_combo = QtWidgets.QComboBox()
        for opt in self.param_options:
            param_combo.addItem(opt)
            i = param_combo.count() - 1
            param_combo.setItemData(i, self.param_descriptions.get(opt, ""), QtCore.Qt.ToolTipRole)
        param_combo.setToolTip("SWMM output parameter to compare")
        if param:
            param_combo.setCurrentText(param)
        remove_btn = QtWidgets.QToolButton(text="Remove")
        remove_btn.clicked.connect(lambda: self._remove_mapping_row(row))
        layout.addWidget(col_combo)
        layout.addWidget(param_combo)
        layout.addWidget(remove_btn)
        self.mapping_rows_layout.addWidget(row)
        self.mapping_rows.append((row, col_combo, param_combo))

    def _remove_mapping_row(self, row: QtWidgets.QWidget) -> None:
        for i, (r, _c, _p) in enumerate(self.mapping_rows):
            if r is row:
                self.mapping_rows.pop(i)
                break
        row.setParent(None)
        row.deleteLater()
        if not self.mapping_rows:
            self._show_example_row()

    def _run(self) -> None:
        outfile = self.out_edit.text().strip()
        obs = self.obs_edit.text().strip()
        element_id = self.id_combo.currentText().strip()
        plot_path = self.plot_edit.text().strip()
        pptx_path = self.pptx_edit.text().strip()
        if not outfile or not obs or not element_id or not plot_path:
            QtWidgets.QMessageBox.warning(
                self, "Missing input", "Please provide all required fields."
            )
            return
        time_cols = [item.text().strip() for item in self.time_list.selectedItems()]
        mappings = [
            (col.currentText().strip(), param.currentText().strip())
            for (_row, col, param) in self.mapping_rows
            if col.currentText().strip()
        ]
        if not time_cols or not mappings:
            QtWidgets.QMessageBox.warning(
                self, "Missing mapping", "Please provide field mappings."
            )
            return
        base = Path(plot_path)
        self.pending_runs.clear()
        for col, param in mappings:
            plot_file = base.with_name(f"{base.stem}_{param}_{col}{base.suffix}")
            args = [
                outfile,
                obs,
                element_id,
                str(plot_file),
                "--item-type",
                "link",
                "--param",
                param,
                "--obs-time-col",
                ",".join(time_cols),
                "--obs-value-col",
                col,
            ]
            if pptx_path:
                args += ["--pptx", pptx_path]
            self.pending_runs.append(args)

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self._start_next_run()

    def _start_next_run(self) -> None:
        if not self.pending_runs:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.progress.setVisible(False)
            return
        args = self.pending_runs.pop(0)
        self.output_box.appendPlainText(
            "Running: compare-hydrographs " + " ".join(shlex.quote(a) for a in args)
        )
        self.process.start("compare-hydrographs", args)

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
        if self.pending_runs:
            self._start_next_run()
        else:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.progress.setVisible(False)

    def _process_error(self, error: QtCore.QProcess.ProcessError) -> None:
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            msg = "Failed to start compare-hydrographs; ensure it is installed and on PATH"
        else:
            msg = f"Process error: {error}"
        self.output_box.appendPlainText(msg)
        self.pending_runs.clear()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self.pending_runs.clear()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("outfile", self.out_edit.text())
        self.settings.setValue("obsfile", self.obs_edit.text())
        self.settings.setValue("element_id", self.id_combo.currentText())
        self.settings.setValue("plot_path", self.plot_edit.text())
        super().closeEvent(event)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = CompareHydrographsWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
