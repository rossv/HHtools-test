#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Extractor GUI — v4
- Multi-file selection + drag/drop
- Smart ID discovery per type with search & checkboxes
- Parameter picker per type with search
- Units-by-dimension controls (simple, not noisy)
- Output controls with filename preview
- Run with progress + logs + Cancel
- "Preview only" mode (NOT called 'dry-run')
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

# Ensure package root is on ``sys.path`` when run as a script
PKG_ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.append(str(PKG_ROOT))

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

# Import core next to this file
# If packaged, adjust as needed
try:
    from hh_tools.extract_timeseries import (
        combine_across_files,
        discover_ids,
        list_possible_params,
        plan_elements,
        process_elements,
    )
except Exception:
    # fallback for dev environment
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from extract_timeseries import (
        combine_across_files,
        discover_ids,
        list_possible_params,
        plan_elements,
        process_elements,
    )

APP_ORG = "HH-Tools"
APP_NAME = "Unified Extractor v4"

ICON_DIR = Path(__file__).with_name("icons")

TYPES = ["node", "link", "subcatchment", "system", "pollutant"]


@dataclass
class SelectionState:
    files: List[str] = field(default_factory=list)
    ids_by_type: Dict[str, List[str]] = field(
        default_factory=lambda: {t: [] for t in TYPES}
    )
    params_by_type: Dict[str, List[str]] = field(
        default_factory=lambda: {t: [] for t in TYPES}
    )
    include_regex: str = ""
    exclude_regex: str = ""
    use_all: bool = False
    union_mode: bool = True  # True=union across files, False=intersection
    # Units
    assume_units: Dict[str, str] = field(
        default_factory=lambda: {
            "flow": "cfs",
            "depth": "ft",
            "head": "ft",
            "velocity": "ft/s",
        }
    )
    to_units: Dict[str, str] = field(default_factory=dict)
    unit_overrides: Dict[str, str] = field(default_factory=dict)
    param_dimension: Dict[str, str] = field(default_factory=dict)
    # Output
    out_format: str = "tsf"
    combine_mode: str = "sep"  # "sep" | "com" | "across"
    output_dir: str = ""
    prefix: str = ""
    suffix: str = ""
    dat_template: str = ""
    tsf_template_sep: str = ""
    tsf_template_com: str = ""
    param_short: Dict[str, str] = field(default_factory=dict)
    label_map: Dict[str, str] = field(default_factory=dict)
    time_format: str = "%m/%d/%Y %H:%M"
    float_format: str = "%.6f"
    pptx_path: str = ""


class FileList(QtWidgets.QListWidget):
    filesChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(self.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDragDropMode(self.DropOnly)
        self.setAlternatingRowColors(True)
        self.viewport().setAcceptDrops(True)
        self.setToolTip("Drop or add .out files to process")

    def add_files(self, paths: List[str]):
        existing = {self.item(i).text() for i in range(self.count())}
        added = False
        for p in paths:
            if p not in existing:
                self.addItem(p)
                added = True
        if added:
            # Notify only when new files were actually appended so downstream
            # auto-discovery logic runs once per real change.
            self.filesChanged.emit()

    def remove_selected(self):
        for item in self.selectedItems():
            self.takeItem(self.row(item))
        self.filesChanged.emit()

    def clear_files(self):
        self.clear()
        self.filesChanged.emit()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if p.lower().endswith(".out"):
                    paths.append(p)
        if paths:
            self.add_files(paths)
        event.acceptProposedAction()


class SearchableList(QtWidgets.QWidget):
    def __init__(
        self, title: str, items: List[str] = None, checkable=True, parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.checkable = checkable
        layout = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(f"Search {title}…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(f"Filter {title}")
        layout.addWidget(self.search)
        self.list = QtWidgets.QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setUniformItemSizes(True)
        self.list.setToolTip(f"Select {title} to include")
        layout.addWidget(self.list)
        self.toolbar = QtWidgets.QHBoxLayout()
        if checkable:
            self.btn_all = QtWidgets.QPushButton("All")
            self.btn_all.setToolTip("Select all")
            self.btn_none = QtWidgets.QPushButton("None")
            self.btn_none.setToolTip("Select none")
            self.btn_invert = QtWidgets.QPushButton("Invert")
            self.btn_invert.setToolTip("Invert selection")
            for b in (self.btn_all, self.btn_none, self.btn_invert):
                self.toolbar.addWidget(b)
            # Small indeterminate progress bar shown during bulk operations
            self.progress = QtWidgets.QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.setVisible(False)
            self.progress.setFixedHeight(self.btn_all.sizeHint().height())
            self.progress.setMaximumWidth(80)
            self.toolbar.addWidget(self.progress)
            self.btn_all.clicked.connect(self._check_all)
            self.btn_none.clicked.connect(self._check_none)
            self.btn_invert.clicked.connect(self._invert)
        self.toolbar.addStretch()
        layout.addLayout(self.toolbar)

        self.search.textChanged.connect(self._filter)

        if items:
            self.set_items(items)

    def set_items(self, items: List[str]):
        self.list.clear()
        for s in items:
            it = QtWidgets.QListWidgetItem(s)
            if self.checkable:
                it.setCheckState(QtCore.Qt.Unchecked)
            self.list.addItem(it)

    def selected(self) -> List[str]:
        if not self.checkable:
            return [
                self.list.item(i).text()
                for i in range(self.list.count())
                if not self.list.item(i).isHidden()
            ]
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == QtCore.Qt.Checked and not it.isHidden():
                out.append(it.text())
        return out

    def _filter(self, text: str):
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(text not in it.text().lower())

    def _set_busy(self, busy: bool):
        if not self.checkable:
            return
        self.progress.setVisible(busy)
        for b in (self.btn_all, self.btn_none, self.btn_invert):
            b.setEnabled(not busy)
        QtWidgets.QApplication.processEvents()

    def _bulk_set(self, func):
        self._set_busy(True)
        self.list.setUpdatesEnabled(False)
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            func(self.list.item(i))
        self.list.blockSignals(False)
        self.list.setUpdatesEnabled(True)
        # trigger downstream count updates once
        if self.list.count():
            self.list.itemChanged.emit(self.list.item(0))
        self._set_busy(False)

    def _check_all(self):
        self._bulk_set(lambda it: it.setCheckState(QtCore.Qt.Checked))

    def _check_none(self):
        self._bulk_set(lambda it: it.setCheckState(QtCore.Qt.Unchecked))

    def _invert(self):
        def toggle(it):
            it.setCheckState(
                QtCore.Qt.Unchecked
                if it.checkState() == QtCore.Qt.Checked
                else QtCore.Qt.Checked
            )

        self._bulk_set(toggle)


class DiscoverWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(dict)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, files: List[str], inc: str, exc: str, union: bool, parent=None):
        super().__init__(parent)
        self.files = files
        self.inc_re = re.compile(inc) if inc else None
        self.exc_re = re.compile(exc) if exc else None
        self.union = union

    def run(self):
        try:
            per_file: Dict[str, Dict[str, List[str]]] = {}
            total = len(self.files) * len(TYPES)
            done = 0
            for f in self.files:
                per_file[f] = {}
                for t in TYPES:
                    ids = discover_ids(f, t)
                    flt = []
                    for i in ids:
                        if self.inc_re and not self.inc_re.search(i):
                            continue
                        if self.exc_re and self.exc_re.search(i):
                            continue
                        flt.append(i)
                    per_file[f][t] = flt
                    done += 1
                    self.progress.emit(done, total)
            result: Dict[str, List[str]] = {}
            for t in TYPES:
                if self.union:
                    result[t] = sorted({i for f in self.files for i in per_file[f][t]})
                else:
                    sets = [set(per_file[f][t]) for f in self.files]
                    result[t] = sorted(list(set.intersection(*sets))) if sets else []
            self.finished.emit(result)
        except Exception as e:
            self.failed.emit(f"{e.__class__.__name__}: {e}")


class Worker(QtCore.QThread):
    msg = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int, int, dict)  # done, total, ctx
    finished_ok = QtCore.pyqtSignal(list)  # written files
    failed = QtCore.pyqtSignal(str)

    def __init__(self, state: SelectionState, plan_only: bool, parent=None):
        super().__init__(parent)
        self.state = state
        self.plan_only = plan_only
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            written: List[str] = []
            planned: List[str] = []

            # Compute total series count for progress
            total = 0
            for f in self.state.files:
                for t in TYPES:
                    ids = self.state.ids_by_type.get(t, [])
                    params = self.state.params_by_type.get(t, [])
                    if t == "system" and ids:
                        ids = ["SYSTEM"]
                    total += (len(ids) or 0) * (len(params) or 0)
            total = max(total, 1)

            done_so_far = 0

            def cb(done, tot, ctx):
                nonlocal done_so_far
                done_so_far += 1
                self.progress.emit(done_so_far, total, ctx)
                if self._cancel:
                    raise RuntimeError("Canceled by user")

            for outfile in self.state.files:
                outdir_root = self.state.output_dir or os.path.dirname(outfile)

                if self.plan_only:
                    for t in TYPES:
                        ids = self.state.ids_by_type.get(t, [])
                        params = self.state.params_by_type.get(t, [])
                        if not ids or not params:
                            continue
                        planned += plan_elements(
                            outfile,
                            t,
                            ids,
                            params,
                            self.state.out_format,
                            self.state.combine_mode,
                            outdir_root,
                            self.state.prefix,
                            self.state.suffix,
                            self.state.dat_template,
                            self.state.tsf_template_sep,
                            self.state.tsf_template_com,
                            self.state.param_short,
                        )
                else:
                    for t in TYPES:
                        ids = self.state.ids_by_type.get(t, [])
                        params = self.state.params_by_type.get(t, [])
                        if not ids or not params:
                            continue
                        paths, _ = process_elements(
                            outfile,
                            t,
                            ids,
                            params,
                            self.state.out_format,
                            self.state.combine_mode,
                            outdir_root,
                            self.state.time_format,
                            self.state.float_format,
                            self.state.prefix,
                            self.state.suffix,
                            self.state.dat_template,
                            self.state.tsf_template_sep,
                            self.state.tsf_template_com,
                            self.state.param_short,
                            self.state.label_map,
                            self.state.param_dimension,
                            self.state.assume_units,
                            self.state.to_units,
                            self.state.unit_overrides,
                            show_progress=False,
                            ppt=None,
                            progress_callback=cb,
                        )
                        written.extend(paths)

            # Post-processing combine
            if not self.plan_only and self.state.combine_mode == "across" and written:
                combine_across_files(
                    written,
                    self.state.out_format,
                    (self.state.output_dir or os.getcwd()),
                )

            self.finished_ok.emit(planned if self.plan_only else written)
        except Exception as e:
            import traceback

            with open("last_error.txt", "w", encoding="utf-8") as fh:
                fh.write(traceback.format_exc())
            self.failed.emit(f"{e.__class__.__name__}: {e}")


class ExtractorWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon(str(ICON_DIR / "extract_timeseries.ico")))
        self.resize(1200, 560)
        self.settings = QtCore.QSettings(APP_ORG, APP_NAME)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main = QtWidgets.QVBoxLayout(central)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        main.addWidget(splitter)

        # Top: controls (tabs per section)
        self.tabs = QtWidgets.QTabWidget()
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)

        # Bottom: run + log
        bottom = QtWidgets.QWidget()
        b_layout = QtWidgets.QVBoxLayout(bottom)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setToolTip("Progress of extraction")
        b_layout.addWidget(self.progress)
        hl = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("Run")
        self.btn_run.setToolTip("Run extraction")
        self.btn_preview = QtWidgets.QPushButton("Preview only")
        self.btn_preview.setToolTip("Show planned filenames without writing files")
        self.btn_open_dir = QtWidgets.QPushButton("Open folder")
        self.btn_open_dir.setToolTip("Open output directory")
        self.btn_help = QtWidgets.QPushButton("Help")
        self.btn_help.setToolTip("Show usage information")
        self.btn_help.clicked.connect(lambda: show_help("extract_timeseries", self))
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.setToolTip("Cancel running task")
        self.btn_cancel.setEnabled(False)
        self.time_label = QtWidgets.QLabel()
        self.time_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        hl.addWidget(self.btn_run)
        hl.addWidget(self.btn_preview)
        hl.addWidget(self.btn_open_dir)
        hl.addWidget(self.btn_help)
        hl.addStretch()
        hl.addWidget(self.time_label)
        hl.addWidget(self.btn_cancel)
        b_layout.addLayout(hl)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        b_layout.addWidget(self.log, 1)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(1, 1)

        # Runtime/ETA timer setup
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_time)
        self._start_time: Optional[float] = None
        self._progress_done = 0
        self._progress_total = 0

        # Section 1: Sources
        self.page_sources = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(self.page_sources)
        self.file_list = FileList()
        lay.addWidget(self.file_list, 1)
        hb = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("Add .out files")
        btn_add.setToolTip("Select SWMM .out files")
        btn_del = QtWidgets.QPushButton("Remove selected")
        btn_del.setToolTip("Remove highlighted files")
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.setToolTip("Clear file list")
        hb.addWidget(btn_add)
        hb.addWidget(btn_del)
        hb.addWidget(btn_clear)
        hb.addStretch()
        lay.addLayout(hb)
        btn_add.clicked.connect(self._choose_files)
        btn_del.clicked.connect(self.file_list.remove_selected)
        btn_clear.clicked.connect(self.file_list.clear_files)
        self.file_list.filesChanged.connect(lambda: self._start_discover_ids(auto=True))
        self.file_list.filesChanged.connect(self._detect_units)
        self.tabs.addTab(self.page_sources, "1) Sources")

        # Section 2: IDs
        self.page_ids = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(self.page_ids)
        self.union_combo = QtWidgets.QComboBox()
        self.union_combo.addItems(["Union across files", "Intersection across files"])
        self.union_combo.setToolTip("How to combine IDs from multiple files")
        self.include_edit = QtWidgets.QLineEdit()
        self.include_edit.setPlaceholderText("Include regex (optional)")
        self.include_edit.setClearButtonEnabled(True)
        self.include_edit.setToolTip("Regular expression to include IDs")
        self.exclude_edit = QtWidgets.QLineEdit()
        self.exclude_edit.setPlaceholderText("Exclude regex (optional)")
        self.exclude_edit.setClearButtonEnabled(True)
        self.exclude_edit.setToolTip("Regular expression to exclude IDs")
        self.btn_discover = QtWidgets.QPushButton("Discover IDs")
        self.btn_discover.setToolTip("Scan files for IDs")
        self.btn_paste = QtWidgets.QPushButton("Paste IDs…")
        self.btn_paste.setToolTip("Paste newline-separated IDs from clipboard")
        self.discover_progress = QtWidgets.QProgressBar()
        self.discover_progress.setVisible(False)
        self.discover_progress.setTextVisible(False)
        grid.addWidget(QtWidgets.QLabel("Multi-file logic:"), 0, 0)
        grid.addWidget(self.union_combo, 0, 1)
        grid.addWidget(self.btn_discover, 0, 2)
        grid.addWidget(self.discover_progress, 0, 3)
        grid.addWidget(self.include_edit, 1, 0, 1, 2)
        grid.addWidget(self.exclude_edit, 1, 2, 1, 2)
        self.id_tabs = QtWidgets.QTabWidget()
        self.id_lists: Dict[str, SearchableList] = {}
        for i, t in enumerate(TYPES):
            w = SearchableList(f"{t} IDs")
            self.id_tabs.addTab(w, t.title())
            self.id_lists[t] = w
            w.list.itemChanged.connect(self._update_id_counts)
        grid.addWidget(self.id_tabs, 2, 0, 1, 4)
        grid.addWidget(self.btn_paste, 3, 0, 1, 1)
        self.id_count_label = QtWidgets.QLabel()
        grid.addWidget(self.id_count_label, 3, 1, 1, 3)
        grid.setRowStretch(2, 1)
        grid.setColumnStretch(3, 1)
        self.tabs.addTab(self.page_ids, "2) IDs")

        # Section 3: Parameters
        self.page_params = QtWidgets.QWidget()
        gridp = QtWidgets.QGridLayout(self.page_params)
        self.param_tabs = QtWidgets.QTabWidget()
        self.param_lists: Dict[str, SearchableList] = {}
        for t in TYPES:
            w = SearchableList(f"{t} parameters")
            self.param_tabs.addTab(w, t.title())
            self.param_lists[t] = w
        gridp.addWidget(self.param_tabs, 0, 0, 1, 3)
        self.tabs.addTab(self.page_params, "3) Parameters")

        # Section 4: Units
        self.page_units = QtWidgets.QWidget()
        fu = QtWidgets.QFormLayout(self.page_units)
        self.units_label = QtWidgets.QLabel()
        fu.addRow(self.units_label)
        self.assume_flow = QtWidgets.QComboBox()
        self.assume_flow.addItems(["", "cfs", "cms", "mgd", "gpm", "l/s"])
        self.assume_flow.setCurrentText("cfs")
        self.assume_flow.setToolTip("Units assumed for flow in inputs")
        self.assume_depth = QtWidgets.QComboBox()
        self.assume_depth.addItems(["", "ft", "m", "in", "cm"])
        self.assume_depth.setCurrentText("ft")
        self.assume_depth.setToolTip("Units assumed for depth in inputs")
        self.assume_head = QtWidgets.QComboBox()
        self.assume_head.addItems(["", "ft", "m", "in", "cm"])
        self.assume_head.setCurrentText("ft")
        self.assume_head.setToolTip("Units assumed for head in inputs")
        self.assume_vel = QtWidgets.QComboBox()
        self.assume_vel.addItems(["", "ft/s", "m/s"])
        self.assume_vel.setCurrentText("ft/s")
        self.assume_vel.setToolTip("Units assumed for velocity in inputs")
        self.to_flow = QtWidgets.QComboBox()
        self.to_flow.addItems(["", "cfs", "cms", "mgd", "gpm", "l/s"])
        self.to_flow.setCurrentText("cfs")
        self.to_flow.setToolTip("Convert flow to this unit")
        self.to_depth = QtWidgets.QComboBox()
        self.to_depth.addItems(["", "ft", "m", "in", "cm"])
        self.to_depth.setCurrentText("ft")
        self.to_depth.setToolTip("Convert depth to this unit")
        self.to_head = QtWidgets.QComboBox()
        self.to_head.addItems(["", "ft", "m", "in", "cm"])
        self.to_head.setCurrentText("ft")
        self.to_head.setToolTip("Convert head to this unit")
        self.to_vel = QtWidgets.QComboBox()
        self.to_vel.addItems(["", "ft/s", "m/s"])
        self.to_vel.setCurrentText("ft/s")
        self.to_vel.setToolTip("Convert velocity to this unit")
        fu.addRow("Assume flow", self.assume_flow)
        fu.addRow("Assume depth", self.assume_depth)
        fu.addRow("Assume head", self.assume_head)
        fu.addRow("Assume velocity", self.assume_vel)
        fu.addRow("To flow", self.to_flow)
        fu.addRow("To depth", self.to_depth)
        fu.addRow("To head", self.to_head)
        fu.addRow("To velocity", self.to_vel)
        self.tabs.addTab(self.page_units, "4) Units")

        # Section 5: Output
        self.page_output = QtWidgets.QWidget()
        fo = QtWidgets.QGridLayout(self.page_output)
        fo.setVerticalSpacing(4)
        fo.setHorizontalSpacing(8)
        fo.setColumnStretch(1, 1)
        fo.setColumnStretch(3, 1)
        self.out_format = QtWidgets.QComboBox()
        self.out_format.addItems(["tsf", "dat", "csv"])
        self.out_format.setToolTip("Output file format")
        self.combine = QtWidgets.QComboBox()
        self.combine.addItem("Separate files per parameter", "sep")
        self.combine.addItem("Combine parameters per element", "com")
        self.combine.addItem("Merge IDs across input files", "across")
        self.combine.setToolTip("How to group parameters into files")
        self.output_dir = QtWidgets.QLineEdit()
        self.output_dir.setClearButtonEnabled(True)
        self.output_dir.setToolTip("Directory where output files are written")
        btn_out = QtWidgets.QPushButton("Browse…")
        btn_out.clicked.connect(self._choose_output_dir)
        btn_out.setToolTip("Select output directory")
        outrow = QtWidgets.QHBoxLayout()
        outrow.setSpacing(6)
        outrow.addWidget(self.output_dir)
        outrow.addWidget(btn_out)
        self.prefix = QtWidgets.QLineEdit()
        self.prefix.setClearButtonEnabled(True)
        self.prefix.setToolTip("Prefix added to filenames")
        self.suffix = QtWidgets.QLineEdit()
        self.suffix.setClearButtonEnabled(True)
        self.suffix.setToolTip("Suffix added to filenames")
        self.dat_template = QtWidgets.QLineEdit()
        self.dat_template.setPlaceholderText("{prefix}{short}_{id}{suffix}.dat")
        self.dat_template.setToolTip("Filename pattern for .dat/.csv outputs")
        self.dat_template.setClearButtonEnabled(True)
        self.tsf_sep = QtWidgets.QLineEdit()
        self.tsf_sep.setPlaceholderText("{prefix}{type}_{id}_{param}{suffix}.tsf")
        self.tsf_sep.setToolTip(
            "Filename pattern when each parameter has its own .tsf file"
        )
        self.tsf_sep.setClearButtonEnabled(True)
        self.tsf_com = QtWidgets.QLineEdit()
        self.tsf_com.setPlaceholderText("{prefix}{type}_{id}{suffix}.tsf")
        self.tsf_com.setToolTip(
            "Filename pattern when parameters are combined into one .tsf"
        )
        self.tsf_com.setClearButtonEnabled(True)
        self.preview_box = QtWidgets.QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setFixedHeight(120)
        self.preview_box.setToolTip("Preview of planned filenames")
        r = 0
        fo.addWidget(QtWidgets.QLabel("Format"), r, 0)
        fo.addWidget(self.out_format, r, 1)
        fo.addWidget(QtWidgets.QLabel("Combine"), r, 2)
        fo.addWidget(self.combine, r, 3)
        r += 1
        fo.addWidget(QtWidgets.QLabel("Output dir"), r, 0)
        fo.addLayout(outrow, r, 1, 1, 3)
        r += 1
        fo.addWidget(QtWidgets.QLabel("Prefix"), r, 0)
        fo.addWidget(self.prefix, r, 1)
        fo.addWidget(QtWidgets.QLabel("Suffix"), r, 2)
        fo.addWidget(self.suffix, r, 3)
        r += 1
        self.template_group = QtWidgets.QGroupBox("Filename templates")
        tpl = QtWidgets.QFormLayout(self.template_group)
        tpl.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        tpl.addRow("DAT/CSV pattern", self.dat_template)
        tpl.addRow("TSF per-parameter pattern", self.tsf_sep)
        tpl.addRow("TSF combined pattern", self.tsf_com)
        fo.addWidget(self.template_group, r, 0, 1, 4)
        r += 1
        fo.addWidget(QtWidgets.QLabel("Planned filenames (preview)"), r, 0)
        fo.addWidget(self.preview_box, r, 1, 1, 3)
        self.tabs.addTab(self.page_output, "5) Output")

        # Wire actions
        self.btn_discover.clicked.connect(lambda: self._start_discover_ids(auto=False))
        self.btn_paste.clicked.connect(self._paste_ids)
        self.btn_run.clicked.connect(lambda: self._run(plan_only=False))
        self.btn_preview.clicked.connect(self._preview)
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        self.btn_cancel.clicked.connect(self._cancel)

        # Restore some settings
        last_dir = self.settings.value("last_dir", "", type=str)
        if last_dir and os.path.isdir(last_dir):
            self.output_dir.setText(self.settings.value("output_dir", last_dir))

        # Timer to update preview when templates/format change
        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setInterval(400)
        self._preview_timer.setSingleShot(True)
        for w in [
            self.out_format,
            self.combine,
            self.output_dir,
            self.prefix,
            self.suffix,
            self.dat_template,
            self.tsf_sep,
            self.tsf_com,
        ]:
            if isinstance(w, QtWidgets.QComboBox):
                w.currentTextChanged.connect(lambda _=None: self._preview_timer.start())
            else:
                w.textChanged.connect(lambda _=None: self._preview_timer.start())

        self.out_format.currentTextChanged.connect(self._update_template_placeholder)
        self.out_format.currentTextChanged.connect(self._update_template_fields)
        self.combine.currentIndexChanged.connect(self._update_template_fields)
        self._update_template_placeholder()
        self._update_template_fields()

        self._update_id_counts()

    # ------------- Helpers -------------

    def _update_template_placeholder(self) -> None:
        fmt = self.out_format.currentText()
        if fmt in ("dat", "csv"):
            ext = fmt
            self.dat_template.setPlaceholderText(
                f"{{prefix}}{{short}}_{{id}}{{suffix}}.{ext}"
            )
            self.dat_template.setToolTip(f"Filename pattern for .{ext} outputs")
        else:
            self.dat_template.setPlaceholderText("")
            self.dat_template.setToolTip("Filename pattern for .dat/.csv outputs")

    def _set_field_active(self, widget: QtWidgets.QLineEdit, active: bool) -> None:
        widget.setReadOnly(not active)
        if active:
            widget.setStyleSheet("")
        else:
            widget.setStyleSheet("background-color: #666; color: #555;")

    def _update_template_fields(self) -> None:
        fmt = self.out_format.currentText()
        mode = self.combine.currentData()
        self._set_field_active(self.dat_template, fmt in ("dat", "csv"))
        self._set_field_active(self.tsf_sep, fmt == "tsf" and mode != "com")
        self._set_field_active(self.tsf_com, fmt == "tsf" and mode == "com")

    def dragEnterEvent(
        self, event: QtGui.QDragEnterEvent
    ) -> None:  # pragma: no cover - GUI
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".out"):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dragMoveEvent(
        self, event: QtGui.QDragMoveEvent
    ) -> None:  # pragma: no cover - GUI
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".out"):
                    event.acceptProposedAction()
                    return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # pragma: no cover - GUI
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if p.lower().endswith(".out"):
                    paths.append(p)
        if paths:
            self.file_list.add_files(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _choose_files(self):
        start = self.settings.value("last_dir", "")
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select SWMM .out files", start, "SWMM .out (*.out)"
        )
        if paths:
            self.file_list.add_files(paths)
            self.settings.setValue("last_dir", os.path.dirname(paths[0]))

    def _choose_output_dir(self):
        start = self.settings.value("output_dir", self.settings.value("last_dir", ""))
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output directory", start
        )
        if path:
            self.output_dir.setText(path)
            self.settings.setValue("output_dir", path)

    def _open_output_dir(self):
        path = self.output_dir.text().strip()
        if path and os.path.isdir(path):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def _start_discover_ids(self, auto: bool = False):
        files = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        if not files:
            for t in TYPES:
                self.id_lists[t].set_items([])
            self._update_id_counts()
            return
        inc = self.include_edit.text().strip()
        exc = self.exclude_edit.text().strip()
        union = self.union_combo.currentIndex() == 0

        # UI: show spinner initially
        self.btn_discover.setEnabled(False)
        self.discover_progress.setVisible(True)
        self.discover_progress.setRange(0, 0)

        # Try to build worker (regex could be invalid)
        try:
            self.discover_worker = DiscoverWorker(files, inc, exc, union)
        except re.error as rex:
            # Bad regex — reset UI and tell user
            self.discover_progress.setRange(0, 1)
            self.discover_progress.setVisible(False)
            self.btn_discover.setEnabled(True)
            QtWidgets.QMessageBox.critical(self, "Invalid regex", str(rex))
            return
        except Exception as e:
            self.discover_progress.setRange(0, 1)
            self.discover_progress.setVisible(False)
            self.btn_discover.setEnabled(True)
            QtWidgets.QMessageBox.critical(
                self, "Discovery setup failed", f"{e.__class__.__name__}: {e}"
            )
            return

        # Make progress determinate when updates arrive
        def on_prog(done: int, total: int):
            self.discover_progress.setRange(0, total or 1)
            self.discover_progress.setValue(done)

        def on_finished(res: Dict[str, List[str]]):
            for t in TYPES:
                self.id_lists[t].set_items(res.get(t, []))
                lst = self.param_lists.get(t)
                if lst and lst.list.count() == 0 and files:
                    lst.set_items(list_possible_params(files[0], t))
            self._update_id_counts()
            self.discover_progress.setRange(0, 1)
            self.discover_progress.setVisible(False)
            self.btn_discover.setEnabled(True)
            if not auto:
                QtWidgets.QMessageBox.information(
                    self,
                    "IDs discovered",
                    "Review each tab and check the IDs you want.",
                )

        def on_failed(msg: str):
            self.discover_progress.setRange(0, 1)
            self.discover_progress.setVisible(False)
            self.btn_discover.setEnabled(True)
            QtWidgets.QMessageBox.critical(self, "Discovery failed", msg)

        self.discover_worker.progress.connect(on_prog)
        self.discover_worker.finished.connect(on_finished)
        self.discover_worker.failed.connect(on_failed)
        self.discover_worker.start()

    def _detect_units(self):
        files = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        if not files:
            self.units_label.setText("")
            return
        f0 = Path(files[0])
        rpt = f0.with_suffix(".rpt")
        if not rpt.exists():
            cands = list(f0.parent.glob("*.rpt"))
            if cands:
                rpt = cands[0]
        detected: Dict[str, str] = {}
        if rpt.exists():
            try:
                with open(rpt, "r", errors="ignore") as fh:
                    for line in fh:
                        ul = line.strip().upper()
                        if ul.startswith("FLOW UNITS"):
                            if "CFS" in ul:
                                detected["flow"] = "cfs"
                            elif "CMS" in ul:
                                detected["flow"] = "cms"
                            elif "MGD" in ul:
                                detected["flow"] = "mgd"
                            elif "GPM" in ul:
                                detected["flow"] = "gpm"
                            elif "LPS" in ul or "L/S" in ul:
                                detected["flow"] = "l/s"
                        elif ul.startswith("LENGTH UNITS"):
                            if "FEET" in ul or "FT" in ul:
                                val = "ft"
                            elif "METERS" in ul or "M" in ul:
                                val = "m"
                            elif "INCH" in ul:
                                val = "in"
                            elif "CENTIM" in ul or "CM" in ul:
                                val = "cm"
                            else:
                                val = ""
                            if val:
                                detected["depth"] = val
                                detected["head"] = val
                        elif ul.startswith("VELOCITY UNITS"):
                            if "FT/S" in ul or "FT/SEC" in ul or "FPS" in ul:
                                detected["velocity"] = "ft/s"
                            elif "M/S" in ul or "MPS" in ul:
                                detected["velocity"] = "m/s"
            except Exception:
                pass
        if detected:
            self.units_label.setText(
                "Detected: "
                + ", ".join(f"{k} {v}" for k, v in detected.items())
                + " (override if needed)"
            )
            if detected.get("flow"):
                self.assume_flow.setCurrentText(detected["flow"])
            if detected.get("depth"):
                self.assume_depth.setCurrentText(detected["depth"])
                self.assume_head.setCurrentText(detected["head"])
                if "velocity" not in detected:
                    detected["velocity"] = (
                        "ft/s" if detected["depth"] == "ft" else "m/s"
                    )
            if detected.get("velocity"):
                self.assume_vel.setCurrentText(detected["velocity"])
        else:
            self.units_label.setText("Detected: none")
        # mirror assumes into target units by default
        self.to_flow.setCurrentText(self.assume_flow.currentText())
        self.to_depth.setCurrentText(self.assume_depth.currentText())
        self.to_head.setCurrentText(self.assume_head.currentText())
        self.to_vel.setCurrentText(self.assume_vel.currentText())

    def _update_id_counts(self):
        counts = []
        total = 0
        for t in TYPES:
            lst = self.id_lists.get(t)
            c = len(lst.selected()) if lst else 0
            counts.append(f"{t.title()}s: {c}")
            total += c
        self.id_count_label.setText(" | ".join(counts) + f" | Total: {total}")

    def _paste_ids(self):
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self,
            "Paste IDs",
            "One ID per line (use type:ID to specify type, else use the active tab's type):",
            "",
        )
        if not ok or not text.strip():
            return
        active_type = TYPES[self.id_tabs.currentIndex()]
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if ":" in s:
                t, i = s.split(":", 1)
            else:
                t, i = active_type, s
            w = self.id_lists.get(t)
            if not w:
                continue
            # add item and select it
            it = QtWidgets.QListWidgetItem(i)
            it.setCheckState(QtCore.Qt.Checked)
            w.list.addItem(it)
        self._update_id_counts()

    def _gather_state(self) -> SelectionState:
        st = SelectionState()
        st.files = [
            self.file_list.item(i).text() for i in range(self.file_list.count())
        ]
        if not st.files:
            raise RuntimeError("No input files selected.")

        for t in TYPES:
            st.ids_by_type[t] = self.id_lists[t].selected()
            st.params_by_type[t] = self.param_lists[t].selected()

        st.include_regex = self.include_edit.text().strip()
        st.exclude_regex = self.exclude_edit.text().strip()
        st.union_mode = self.union_combo.currentIndex() == 0

        # Units
        st.assume_units = {
            "flow": self.assume_flow.currentText(),
            "depth": self.assume_depth.currentText(),
            "head": self.assume_head.currentText(),
            "velocity": self.assume_vel.currentText(),
        }
        st.to_units = {
            "flow": self.to_flow.currentText(),
            "depth": self.to_depth.currentText(),
            "head": self.to_head.currentText(),
            "velocity": self.to_vel.currentText(),
        }

        # Output
        st.out_format = self.out_format.currentText()
        st.combine_mode = self.combine.currentData()
        st.output_dir = self.output_dir.text().strip()
        p = self.prefix.text().strip()
        s = self.suffix.text().strip()
        if p and not p.endswith("_"):
            p += "_"
        if s and not s.startswith("_"):
            s = "_" + s
        st.prefix = p
        st.suffix = s
        st.dat_template = self.dat_template.text().strip()
        st.tsf_template_sep = self.tsf_sep.text().strip()
        st.tsf_template_com = self.tsf_com.text().strip()
        return st

    def _preview(self):
        try:
            st = self._gather_state()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Missing inputs", str(e))
            return
        self.preview_box.clear()
        # We don't need a thread for planning; it's fast
        planned_all: List[str] = []
        for f in st.files:
            outdir_root = st.output_dir or os.path.dirname(f)
            for t in TYPES:
                ids = st.ids_by_type.get(t, [])
                params = st.params_by_type.get(t, [])
                if not ids or not params:
                    continue
                planned = plan_elements(
                    f,
                    t,
                    ids,
                    params,
                    st.out_format,
                    st.combine_mode,
                    outdir_root,
                    st.prefix,
                    st.suffix,
                    st.dat_template,
                    st.tsf_template_sep,
                    st.tsf_template_com,
                    st.param_short,
                )
                planned_all.extend(planned)
        self.preview_box.setPlainText(
            "\n".join(
                planned_all[:500]
                + (["… (truncated)"] if len(planned_all) > 500 else [])
            )
        )

    def _run(self, plan_only: bool):
        try:
            st = self._gather_state()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Missing inputs", str(e))
            return

        # Require at least one element and parameter selection
        has_selection = any(
            st.ids_by_type.get(t) and st.params_by_type.get(t) for t in TYPES
        )
        if not has_selection:
            self.log.appendPlainText(
                "Please select at least one element and parameter before running."
            )
            return

        # Param discovery on demand if lists are empty
        for t in TYPES:
            lst = self.param_lists[t]
            if lst.list.count() == 0 and st.files:
                # discover from first file
                lst.set_items(list_possible_params(st.files[0], t))

        self.log.clear()
        import numpy
        import pandas

        msg = [
            f"numpy={numpy.__version__}",
            f"pandas={pandas.__version__}",
        ]
        try:
            import swmmtoolbox as s

            try:
                from importlib.metadata import version

                swmm_ver = version("swmm-toolbox")
            except Exception:
                swmm_ver = getattr(s, "__version__", "unknown")
            msg.insert(0, f"swmmtoolbox={swmm_ver}")
        except Exception as e:
            msg.insert(0, f"swmmtoolbox import failed: {e}")
        self.log.appendPlainText("Versions: " + " ".join(msg))
        self.btn_run.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.time_label.setText("Runtime: 00:00:00   ETA: --:--:--")
        self._start_time = time.monotonic()
        self._progress_done = 0
        self._progress_total = 0
        self._timer.start()

        self.worker = Worker(st, plan_only)
        self.worker.msg.connect(lambda m: self.log.appendPlainText(m))

        def on_prog(done, total, ctx):
            pct = int(done * 100 / max(total, 1))
            self.progress.setValue(pct)
            self.progress.setFormat(
                f"{pct}% — {Path(ctx.get('file','')).name} → {ctx.get('type','')}:{ctx.get('id','')} {ctx.get('param','')}"
            )
            self._progress_done = done
            self._progress_total = total

        self.worker.progress.connect(on_prog)

        def on_ok(paths: List[str]):
            self.log.appendPlainText(
                f"Completed. {len(paths)} {'planned' if plan_only else 'files written'}"
            )
            if not plan_only and st.combine_mode == "across":
                self.log.appendPlainText(
                    "Combined outputs generated in 'combined' subfolder."
                )
            self.btn_run.setEnabled(True)
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.progress.setValue(100)
            self._progress_done = self._progress_total
            self._timer.stop()
            self._update_time()

        self.worker.finished_ok.connect(on_ok)

        def on_fail(msg: str):
            self.log.appendPlainText("ERROR: " + msg)
            self.btn_run.setEnabled(True)
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self._timer.stop()
            self._update_time()

        self.worker.failed.connect(on_fail)
        self.worker.start()

    def _fmt_secs(self, secs: float) -> str:
        secs = int(secs)
        return f"{secs // 3600:02}:{secs % 3600 // 60:02}:{secs % 60:02}"

    def _update_time(self) -> None:
        if self._start_time is None:
            return
        elapsed = time.monotonic() - self._start_time
        eta = "--:--:--"
        if self._progress_total > 0:
            if 0 < self._progress_done < self._progress_total:
                remaining = (
                    elapsed
                    * (self._progress_total - self._progress_done)
                    / self._progress_done
                )
                eta = self._fmt_secs(remaining)
            elif self._progress_done >= self._progress_total:
                eta = "00:00:00"
        runtime = self._fmt_secs(elapsed)
        self.time_label.setText(f"Runtime: {runtime}   ETA: {eta}")

    def _cancel(self):
        if hasattr(self, "worker"):
            self.worker.cancel()
            self.log.appendPlainText("Cancel requested…")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # pragma: no cover - GUI
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = ExtractorWindow()
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
