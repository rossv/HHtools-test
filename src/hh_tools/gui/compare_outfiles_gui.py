"""GUI wrapper around the compare-outfiles command line tool."""

from __future__ import annotations

import os
import shlex
import sys
import tempfile
from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5 import QtCore, QtGui, QtWidgets

from hh_tools.compare_outfiles import extract_series
from hh_tools.extract_timeseries import discover_ids, list_possible_params
from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

ICON_DIR = Path(__file__).with_name("icons")


def plot_series(
    file1: str,
    file2: str,
    item_type: str,
    element_id: str,
    param: str,
    fig: Figure | None = None,
) -> Figure:
    """Return a matplotlib figure comparing two series."""

    fig = fig or Figure()
    ax = fig.add_subplot(111)
    try:
        a = extract_series(file1, item_type, element_id, param)
        b = extract_series(file2, item_type, element_id, param)
        if not a.empty:
            ax.plot(pd.to_datetime(a["Datetime"]), a["value"], label="File 1")
        if not b.empty:
            ax.plot(pd.to_datetime(b["Datetime"]), b["value"], label="File 2")
    except Exception:
        pass
    ax.set_xlabel("Datetime")
    ax.set_ylabel(param)
    ax.legend()
    fig.autofmt_xdate()
    return fig


class SearchableList(QtWidgets.QWidget):
    def __init__(
        self, title: str, items: list[str] | None = None, parent: QtWidgets.QWidget | None = None
    ):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(f"Search {title}…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(f"Filter {title}")
        layout.addWidget(self.search)
        self.list = QtWidgets.QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setToolTip(f"Select {title}")
        layout.addWidget(self.list)
        if items:
            self.set_items(items)
        self.search.textChanged.connect(self._filter)

    def set_items(self, items: list[str]) -> None:
        self.list.clear()
        for s in items:
            it = QtWidgets.QListWidgetItem(s)
            it.setCheckState(QtCore.Qt.Unchecked)
            self.list.addItem(it)

    def selected(self) -> list[str]:
        out: list[str] = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == QtCore.Qt.Checked and not it.isHidden():
                out.append(it.text())
        return out

    def _filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(text not in it.text().lower())


class CompareOutfilesWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Compare Out Files")
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "compare_outfiles.ico")))

        self.settings = QtCore.QSettings("HHTools", self.__class__.__name__)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        main = QtWidgets.QVBoxLayout(self)
        self.menu_bar = QtWidgets.QMenuBar()
        main.setMenuBar(self.menu_bar)
        export_menu = self.menu_bar.addMenu("Export")
        export_menu.addAction("Export Table", self._export_table)
        export_menu.addAction("Export Plot", self._export_plot)

        form = QtWidgets.QFormLayout()
        main.addLayout(form)

        # File 1
        self.file1_edit = QtWidgets.QLineEdit()
        self.file1_edit.setObjectName("file1")
        self.file1_edit.setToolTip("Path to first .out file")
        self.file1_edit.setText(self.settings.value("file1", ""))
        browse1 = QtWidgets.QPushButton("Browse")
        browse1.setToolTip("Browse for first .out file")
        browse1.clicked.connect(lambda: self._choose_file(self.file1_edit))
        f1_layout = QtWidgets.QHBoxLayout()
        f1_layout.addWidget(self.file1_edit)
        f1_layout.addWidget(browse1)
        form.addRow("File 1", f1_layout)

        # File 2
        self.file2_edit = QtWidgets.QLineEdit()
        self.file2_edit.setObjectName("file2")
        self.file2_edit.setToolTip("Path to second .out file")
        self.file2_edit.setText(self.settings.value("file2", ""))
        browse2 = QtWidgets.QPushButton("Browse")
        browse2.setToolTip("Browse for second .out file")
        browse2.clicked.connect(lambda: self._choose_file(self.file2_edit))
        f2_layout = QtWidgets.QHBoxLayout()
        f2_layout.addWidget(self.file2_edit)
        f2_layout.addWidget(browse2)
        form.addRow("File 2", f2_layout)

        # Type
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["node", "link", "subcatchment", "system"])
        self.type_combo.setToolTip("Object type to compare")
        form.addRow("Type", self.type_combo)

        # IDs and params
        self.ids_list = SearchableList("IDs")
        self.ids_list.setToolTip("Select IDs to include")
        self.discover_btn = QtWidgets.QPushButton("Discover")
        self.discover_btn.setToolTip("Scan files for IDs")
        self.discover_btn.clicked.connect(self._discover_ids)
        id_layout = QtWidgets.QHBoxLayout()
        id_layout.addWidget(self.ids_list, 1)
        id_layout.addWidget(self.discover_btn)
        form.addRow("IDs", id_layout)

        self.params_list = SearchableList("Parameters")
        self.params_list.setToolTip("Select parameters to compare")
        self.params_btn = QtWidgets.QPushButton("Discover")
        self.params_btn.setToolTip("Scan files for parameters")
        self.params_btn.clicked.connect(self._discover_params)
        param_layout = QtWidgets.QHBoxLayout()
        param_layout.addWidget(self.params_list, 1)
        param_layout.addWidget(self.params_btn)
        form.addRow("Params", param_layout)

        # Run/Cancel buttons
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.setToolTip("Run comparison")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("Cancel running comparison")
        self.cancel_btn.clicked.connect(self._cancel)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(lambda: show_help("compare_outfiles", self))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.help_btn)
        form.addRow(btn_row)

        # Progress indicator
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setToolTip("Shows progress while comparing")
        form.addRow(self.progress)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main.addWidget(splitter, 1)

        # ID/param list
        self.pair_list = QtWidgets.QListWidget()
        self.pair_list.setToolTip("Available ID/parameter pairs")
        self.pair_list.itemSelectionChanged.connect(self._plot_selected)
        splitter.addWidget(self.pair_list)

        # Middle section: table of comparison results
        table_widget = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_widget)
        splitter.addWidget(table_widget)

        self.table_view = QtWidgets.QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setToolTip("Summary of comparison results")
        table_layout.addWidget(self.table_view, 1)

        self.export_table_btn = QtWidgets.QPushButton("Export Table")
        self.export_table_btn.setToolTip("Export table to CSV")
        self.export_table_btn.clicked.connect(self._export_table)
        table_btn_row = QtWidgets.QHBoxLayout()
        table_btn_row.addWidget(self.export_table_btn)
        table_btn_row.addStretch(1)
        table_layout.addLayout(table_btn_row)

        # Right section: plot of selected pair
        plot_widget = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_widget)
        splitter.addWidget(plot_widget)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setToolTip("Plot of selected ID/parameter pair")
        plot_layout.addWidget(self.canvas, 1)

        self.export_plot_btn = QtWidgets.QPushButton("Export Plot")
        self.export_plot_btn.setToolTip("Export current plot to image")
        self.export_plot_btn.clicked.connect(self._export_plot)
        plot_btn_row = QtWidgets.QHBoxLayout()
        plot_btn_row.addWidget(self.export_plot_btn)
        plot_btn_row.addStretch(1)
        plot_layout.addLayout(plot_btn_row)

        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

        # Output display
        self.output_box = QtWidgets.QPlainTextEdit(readOnly=True)
        self.output_box.setToolTip("Displays log output from comparison")
        main.addWidget(self.output_box)

        # Subprocess handling
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

    def _choose_file(self, target: QtWidgets.QLineEdit) -> None:
        start = self.settings.value(
            target.objectName(), self.settings.value("last_dir", "")
        )
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select .out file", start)
        if path:
            target.setText(path)
            self.settings.setValue(target.objectName(), path)
            self.settings.setValue("last_dir", str(Path(path).parent))

    def _discover_ids(self) -> None:
        file1 = self.file1_edit.text().strip()
        file2 = self.file2_edit.text().strip()
        if not file1 or not file2:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing files",
                "Please choose both files before discovering IDs.",
            )
            return
        item_type = self.type_combo.currentText()
        ids1 = discover_ids(file1, item_type)
        ids2 = discover_ids(file2, item_type)
        ids = sorted(set(ids1) & set(ids2))
        if not ids:
            QtWidgets.QMessageBox.information(
                self, "No IDs", "No common IDs found for the selected type."
            )
            return
        self.ids_list.set_items(ids)

    def _discover_params(self) -> None:
        file1 = self.file1_edit.text().strip()
        file2 = self.file2_edit.text().strip()
        if not file1 or not file2:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing files",
                "Please choose both files before discovering parameters.",
            )
            return
        item_type = self.type_combo.currentText()
        p1 = list_possible_params(file1, item_type)
        p2 = list_possible_params(file2, item_type)
        params = sorted(set(p1) & set(p2))
        if not params:
            QtWidgets.QMessageBox.information(
                self,
                "No Parameters",
                "No common parameters found for the selected type.",
            )
            return
        self.params_list.set_items(params)

    def _run(self) -> None:
        file1 = self.file1_edit.text().strip()
        file2 = self.file2_edit.text().strip()
        if not file1 or not file2:
            QtWidgets.QMessageBox.warning(
                self, "Missing files", "Please choose both files."
            )
            return
        args: list[str] = [file1, file2, "--type", self.type_combo.currentText()]
        ids = self.ids_list.selected()
        if ids:
            args.extend(["--ids", ",".join(ids)])
        params = self.params_list.selected()
        if params:
            args.extend(["--params", ",".join(params)])
        self.output_box.appendPlainText(
            "Running: compare-outfiles " + " ".join(shlex.quote(a) for a in args)
        )
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.report_path = Path(tempfile.mkstemp(suffix=".csv")[1])
        args.extend(["--output", str(self.report_path)])
        self.process.start(sys.executable, ["-m", "hh_tools.compare_outfiles", *args])

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
        if code == 0:
            self._load_results()

    def _cancel(self) -> None:
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.output_box.appendPlainText("Canceled")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _load_results(self) -> None:
        try:
            df = pd.read_csv(self.report_path)
        except Exception as exc:
            self.output_box.appendPlainText(f"Could not load results: {exc}")
            return
        self.df = df
        model = QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(df.columns.tolist())
        for _, row in df.iterrows():
            items = [QtGui.QStandardItem(str(row[c])) for c in df.columns]
            model.appendRow(items)
        self.table_view.setModel(model)
        self.table_view.resizeColumnsToContents()

        self.pair_list.clear()
        for _, row in df.iterrows():
            text = f"{row['id']} / {row['param']}"
            it = QtWidgets.QListWidgetItem(text)
            it.setData(QtCore.Qt.UserRole, (row["id"], row["param"]))
            self.pair_list.addItem(it)

    def _plot_selected(self) -> None:
        items = self.pair_list.selectedItems()
        if not items:
            return
        element_id, param = items[0].data(QtCore.Qt.UserRole)
        self.figure.clear()
        plot_series(
            self.file1_edit.text().strip(),
            self.file2_edit.text().strip(),
            self.type_combo.currentText(),
            element_id,
            param,
            fig=self.figure,
        )
        ax = self.figure.axes[0]
        self._apply_theme_to_mpl(ax)
        self.figure.autofmt_xdate()
        self.canvas.draw()

    def _export_table(self) -> None:
        if not hasattr(self, "df"):
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export table to CSV", "comparison_report.csv"
        )
        if path:
            try:
                self.df.to_csv(path, index=False)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Export failed", str(exc))

    def _export_plot(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export plot image",
            "plot.png",
            filter="PNG Files (*.png);;All Files (*)",
        )
        if path:
            try:
                self.figure.savefig(path)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Export failed", str(exc))

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

    def closeEvent(
        self, event: QtGui.QCloseEvent
    ) -> None:  # pragma: no cover - GUI only
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("file1", self.file1_edit.text())
        self.settings.setValue("file2", self.file2_edit.text())
        super().closeEvent(event)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = CompareOutfilesWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":
    main()
