"""PyQt5 front-end for :mod:`hh_tools.review_flow_data`."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.gui.theme import apply_dark_palette

ICON_DIR = Path(__file__).with_name("icons")


class ReviewFlowWindow(QtWidgets.QMainWindow):
    """Collect parameters for the flow review tool."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Review Flow Data")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "review_flow_data.ico")))
        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        toolbar = QtWidgets.QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        open_act = QtWidgets.QAction(
            self.style().standardIcon(QtWidgets.QStyle.SP_DialogOpenButton),
            "Open",
            self,
        )
        open_act.triggered.connect(self._choose_input)
        toolbar.addAction(open_act)

        save_act = QtWidgets.QAction(
            self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton),
            "Save",
            self,
        )
        save_act.triggered.connect(self._choose_output)
        toolbar.addAction(save_act)

        toolbar.addSeparator()

        self.run_act = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "play.svg")), "Run", self
        )
        self.run_act.setToolTip("Run flow data review")
        self.run_act.triggered.connect(self._run)
        toolbar.addAction(self.run_act)

        toolbar.addSeparator()

        help_act = QtWidgets.QAction(
            self.style().standardIcon(QtWidgets.QStyle.SP_DialogHelpButton),
            "Help",
            self,
        )
        help_act.triggered.connect(self._show_help)
        toolbar.addAction(help_act)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setCentralWidget(splitter)

        left = QtWidgets.QWidget()
        left_v = QtWidgets.QVBoxLayout(left)

        gb_paths = QtWidgets.QGroupBox("Paths")
        gb_paths.setFlat(True)
        paths_form = QtWidgets.QFormLayout(gb_paths)
        # Input file
        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setObjectName("input_path")
        self.input_edit.setToolTip("Path to input data file")
        self.input_edit.setText(self.settings.value("input_path", ""))
        browse_in = QtWidgets.QPushButton("Browse")
        browse_in.setToolTip("Browse for input file")
        browse_in.clicked.connect(self._choose_input)
        in_layout = QtWidgets.QHBoxLayout()
        in_layout.addWidget(self.input_edit)
        in_layout.addWidget(browse_in)
        paths_form.addRow("Input file", in_layout)
        # Output file
        self.output_edit = QtWidgets.QLineEdit()
        self.output_edit.setObjectName("output_path")
        self.output_edit.setToolTip("Path to output TSF file")
        self.output_edit.setText(self.settings.value("output_path", ""))
        browse_out = QtWidgets.QPushButton("Browse")
        browse_out.setToolTip("Browse for output TSF file")
        browse_out.clicked.connect(self._choose_output)
        out_layout = QtWidgets.QHBoxLayout()
        out_layout.addWidget(self.output_edit)
        out_layout.addWidget(browse_out)
        paths_form.addRow("Output TSF", out_layout)

        gb_cols = QtWidgets.QGroupBox("Columns")
        gb_cols.setFlat(True)
        cols_form = QtWidgets.QFormLayout(gb_cols)
        self.available_cols: list[str] = []
        self.time_col = QtWidgets.QComboBox()
        self.time_col.setEditable(True)
        self.time_col.setToolTip("Column name for timestamps")
        self.flow_col = QtWidgets.QComboBox()
        self.flow_col.setEditable(True)
        self.flow_col.setToolTip("Column name for flow values")
        self.depth_col = QtWidgets.QComboBox()
        self.depth_col.setEditable(True)
        self.depth_col.setToolTip("Column name for depth values")
        self.vel_col = QtWidgets.QComboBox()
        self.vel_col.setEditable(True)
        self.vel_col.setToolTip("Column name for velocity values")
        cols_form.addRow("Time column", self.time_col)
        cols_form.addRow("Flow column", self.flow_col)
        cols_form.addRow("Depth column", self.depth_col)
        cols_form.addRow("Velocity column", self.vel_col)

        gb_opts = QtWidgets.QGroupBox("Options")
        gb_opts.setFlat(True)
        opts_form = QtWidgets.QFormLayout(gb_opts)
        self.resample = QtWidgets.QLineEdit()
        self.resample.setToolTip("Pandas frequency string for downsampling")
        opts_form.addRow("Downsample freq", self.resample)

        self.interp_check = QtWidgets.QCheckBox("Interpolate gaps/spikes")
        self.interp_check.setChecked(True)
        self.interp_check.setToolTip("Enable basic cleaning of data")
        opts_form.addRow(self.interp_check)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setToolTip("Shows progress while reviewing")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("Cancel running review")
        self.cancel_btn.clicked.connect(self._cancel)

        for gb in (gb_paths, gb_cols):
            frame = QtWidgets.QFrame()
            frame.setObjectName("card")
            fl = QtWidgets.QVBoxLayout(frame)
            fl.setContentsMargins(12, 12, 12, 12)
            fl.addWidget(gb)
            left_v.addWidget(frame)

        preview_frame = QtWidgets.QFrame()
        preview_frame.setObjectName("card")
        pv_layout = QtWidgets.QVBoxLayout(preview_frame)
        pv_layout.setContentsMargins(12, 12, 12, 12)
        self.preview_table = QtWidgets.QTableView()
        self.preview_table.setToolTip("Preview of input data")
        self.preview_table.setMinimumHeight(120)
        pv_layout.addWidget(self.preview_table)
        left_v.addWidget(preview_frame)

        frame = QtWidgets.QFrame()
        frame.setObjectName("card")
        fl = QtWidgets.QVBoxLayout(frame)
        fl.setContentsMargins(12, 12, 12, 12)
        fl.addWidget(gb_opts)
        left_v.addWidget(frame)

        left_v.addWidget(self.progress)
        left_v.addWidget(self.cancel_btn)
        left_v.addStretch(1)

        preview = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(preview)
        pv.setContentsMargins(4, 4, 4, 4)
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        # Apply theme to an initial blank axis then clear
        ax = self.figure.add_subplot(111)
        self._apply_theme_to_mpl(ax)
        self.figure.clear()
        pv.addWidget(self.canvas, 3)
        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        self.output_box.setToolTip("Displays output from the review process")
        pv.addWidget(self.output_box, 1)

        splitter.addWidget(left)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

    def _choose_input(self) -> None:
        start = self.settings.value("input_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select input file", start
        )
        if path:
            self.input_edit.setText(path)
            self.settings.setValue("input_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))
            self._load_columns(path)

    def _choose_output(self) -> None:
        start = self.settings.value("output_path", self.settings.value("last_dir", ""))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Select output TSF",
            start,
            filter="TSF Files (*.tsf)",
        )
        if path:
            self.output_edit.setText(path)
            self.settings.setValue("output_path", path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _run(self) -> None:
        inp = self.input_edit.text().strip()
        outp = self.output_edit.text().strip()
        if not inp or not outp:
            QtWidgets.QMessageBox.warning(
                self, "Missing paths", "Please choose input and output files."
            )
            return
        if inp != getattr(self, "_loaded_path", None):
            self._load_columns(inp)
        time_col = self.time_col.currentText().strip()
        flow_col = self.flow_col.currentText().strip()
        depth_col = self.depth_col.currentText().strip()
        vel_col = self.vel_col.currentText().strip()
        if not time_col:
            QtWidgets.QMessageBox.warning(
                self, "Missing columns", "Please select a time column."
            )
            return
        chosen = [c for c in [flow_col, depth_col, vel_col] if c]
        if not chosen:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing columns",
                "Select at least one flow/depth/velocity column.",
            )
            return
        if self.available_cols:
            missing = [c for c in [time_col, *chosen] if c not in self.available_cols]
            if missing:
                QtWidgets.QMessageBox.warning(
                    self, "Missing columns", f"Columns not found: {', '.join(missing)}"
                )
                return
        args: list[str] = [inp, "--time-col", time_col]
        if flow_col:
            args.extend(["--flow-col", flow_col])
        if depth_col:
            args.extend(["--depth-col", depth_col])
        if vel_col:
            args.extend(["--velocity-col", vel_col])
        if self.resample.text():
            args.extend(["--resample", self.resample.text()])
        if not self.interp_check.isChecked():
            args.append("--no-interpolate")
        args.extend(["--output", outp])
        self.output_box.appendPlainText(
            "Running: review-flow-data " + " ".join(shlex.quote(a) for a in args)
        )
        self.progress.setVisible(True)
        self.run_act.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.process.start(sys.executable, ["-m", "hh_tools.review_flow_data", *args])

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
        self.run_act.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)
        if code == 0:
            self._plot_output()

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self.run_act.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _show_help(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Review Flow Data",
            (
                "Provide input/output paths and column names, then use Run to "
                "review the data."
            ),
        )

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("input_path", self.input_edit.text())
        self.settings.setValue("output_path", self.output_edit.text())
        super().closeEvent(event)

    def _load_columns(self, path: str) -> None:
        try:
            ext = Path(path).suffix.lower()
            if ext in {".xls", ".xlsx"}:
                df = pd.read_excel(path, nrows=0)
            else:
                df = pd.read_csv(path, sep=None, engine="python", nrows=0)
            cols = list(df.columns)
        except Exception as exc:
            cols = []
            QtWidgets.QMessageBox.warning(self, "Column load error", str(exc))
        self.available_cols = cols
        for combo in (self.time_col, self.flow_col, self.depth_col, self.vel_col):
            prev = combo.currentText()
            combo.clear()
            combo.addItems(cols)
            combo.setCurrentText(prev if prev in cols else "")
        self._loaded_path = path
        self._load_preview(path)

    def _load_preview(self, path: str, n: int = 5) -> None:
        try:
            ext = Path(path).suffix.lower()
            if ext in {".xls", ".xlsx"}:
                df = pd.read_excel(path, nrows=n)
            else:
                df = pd.read_csv(path, sep=None, engine="python", nrows=n)
        except Exception as exc:
            df = pd.DataFrame()
            QtWidgets.QMessageBox.warning(self, "Preview load error", str(exc))
        # Keep a reference to the model so it is not garbage collected.
        # Without this, the view may attempt to access a deleted C++ object
        # once this method returns.
        self.preview_model = QtGui.QStandardItemModel(self)
        self.preview_model.setHorizontalHeaderLabels(df.columns.tolist())
        for _, row in df.iterrows():
            items = [QtGui.QStandardItem(str(row[c])) for c in df.columns]
            self.preview_model.appendRow(items)
        self.preview_table.setModel(self.preview_model)
        self.preview_table.resizeColumnsToContents()

    def _plot_output(self) -> None:
        outp = Path(self.output_edit.text().strip())
        if not outp.exists():
            return
        try:
            df = pd.read_csv(outp, sep="\t")
            if "Datetime" in df.columns:
                df["Datetime"] = pd.to_datetime(df["Datetime"])
                df = df.set_index("Datetime")
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            df.plot(ax=ax)
            ax.set_xlabel("Time")
            ax.set_ylabel("Value")
            self._apply_theme_to_mpl(ax)
            self.canvas.draw()
        except Exception as exc:
            self.output_box.appendPlainText(f"Plot error: {exc}")

    def _apply_theme_to_mpl(self, ax):
        pal = self.palette()
        bg = pal.window().color()
        base = pal.base().color()
        text = pal.windowText().color()

        def rgb(col):
            return (col.red() / 255.0, col.green() / 255.0, col.blue() / 255.0)

        self.figure.set_facecolor(rgb(bg))
        ax.set_facecolor(rgb(base))
        ax.tick_params(colors=rgb(text))
        ax.xaxis.label.set_color(rgb(text))
        ax.yaxis.label.set_color(rgb(text))
        ax.title.set_color(rgb(text))
        for spine in ax.spines.values():
            spine.set_color(rgb(text))


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = ReviewFlowWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
