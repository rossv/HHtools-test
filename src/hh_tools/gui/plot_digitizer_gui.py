#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot Digitizer GUI.

Digitize X/Y points from plot images after calibrating axes.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

# Ensure package root on sys.path when run as a script
PKG_ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:  # pragma: no cover - convenience for script usage
    sys.path.append(str(PKG_ROOT))

from hh_tools.gui.theme import apply_dark_palette
from hh_tools.gui.help_links import show_help

APP_ORG = "HH-Tools"
APP_NAME = "Plot Digitizer"
DESCRIPTION = "Digitize points from plot images."


class ZoomableView(QtWidgets.QGraphicsView):
    """Graphics view supporting wheel zoom and space-bar panning."""

    clicked = QtCore.pyqtSignal(QtCore.QPointF)

    def __init__(self, scene: QtWidgets.QGraphicsScene):
        super().__init__(scene)
        self.setRenderHints(self.renderHints() | QtGui.QPainter.Antialiasing)
        self.setDragMode(self.NoDrag)
        self.setTransformationAnchor(self.AnchorUnderMouse)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self.dragMode() == self.NoDrag:
            self.clicked.emit(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Space and self.dragMode() != self.ScrollHandDrag:
            self.setDragMode(self.ScrollHandDrag)
            self.viewport().setCursor(QtCore.Qt.ClosedHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Space and self.dragMode() == self.ScrollHandDrag:
            self.setDragMode(self.NoDrag)
            self.viewport().unsetCursor()
        super().keyReleaseEvent(event)


class Digitizer(QtWidgets.QMainWindow):
    """Main window for the plot digitizer."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        # Graphics scene/view
        self.scene = QtWidgets.QGraphicsScene(self)
        self.pix_item: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self.view = ZoomableView(self.scene)
        self.view.clicked.connect(self.on_scene_click)

        # Table for points
        self.table = QtWidgets.QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["X", "Y"])

        splitter = QtWidgets.QSplitter(self)
        splitter.addWidget(self.view)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        container = QtWidgets.QWidget(self)
        lay = QtWidgets.QVBoxLayout(container)
        lay.addWidget(splitter)
        self.setCentralWidget(container)

        # Toolbar
        tb = self.addToolBar("Main")

        act_open = tb.addAction("Open Image…")
        act_open.triggered.connect(self.open_image)

        self.act_cal_x = tb.addAction("Calibrate X")
        self.act_cal_x.setCheckable(True)
        self.act_cal_x.triggered.connect(lambda: self.start_calibrate("x"))

        self.act_cal_y = tb.addAction("Calibrate Y")
        self.act_cal_y.setCheckable(True)
        self.act_cal_y.triggered.connect(lambda: self.start_calibrate("y"))

        self.act_digitize = tb.addAction("Digitize")
        self.act_digitize.setCheckable(True)

        self.chk_xlog = QtWidgets.QCheckBox("X log10")
        self.chk_ylog = QtWidgets.QCheckBox("Y log10")
        tb.addWidget(self.chk_xlog)
        tb.addWidget(self.chk_ylog)

        act_clear = tb.addAction("Clear Points")
        act_clear.triggered.connect(self.clear_points)

        act_export = tb.addAction("Export CSV…")
        act_export.triggered.connect(self.export_csv)

        tb.addSeparator()
        help_act = tb.addAction("Help")
        help_act.triggered.connect(lambda: show_help("plot_digitizer", self))

        # Status bar
        self.status = self.statusBar()
        self.status.showMessage("Open an image. Space=pan, wheel=zoom.")

        # Calibration state
        self.cal_state: Optional[dict] = None
        self.ax = self.bx = self.ay = self.by = None

        # Marker visuals
        color = QtGui.QColor(220, 20, 60)
        self.point_pen = QtGui.QPen(color)
        self.point_brush = QtGui.QBrush(color)
        self.point_radius = 3
        self.marker_items: list[QtWidgets.QGraphicsEllipseItem] = []

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def load_image(self, path: str) -> None:
        pm = QtGui.QPixmap(path)
        if pm.isNull():
            QtWidgets.QMessageBox.warning(self, "Load failed", "Could not load image.")
            return
        self.scene.clear()
        self.marker_items.clear()
        self.pix_item = QtWidgets.QGraphicsPixmapItem(pm)
        self.scene.addItem(self.pix_item)
        self.scene.setSceneRect(pm.rect())
        self.view.resetTransform()
        self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
        self.status.showMessage("Image loaded. Calibrate axes, then enable Digitize.")

        # Reset calibration
        self.ax = self.bx = self.ay = self.by = None
        self.act_cal_x.setChecked(False)
        self.act_cal_y.setChecked(False)
        self.act_digitize.setChecked(False)
        self.table.setRowCount(0)

    def open_image(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Curve Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if path:
            self.load_image(path)

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------
    def start_calibrate(self, axis: str) -> None:
        if not self.pix_item:
            QtWidgets.QMessageBox.information(self, "No image", "Open an image first.")
            if axis == "x":
                self.act_cal_x.setChecked(False)
            else:
                self.act_cal_y.setChecked(False)
            return
        self.cal_state = {"axis": axis, "points": []}
        if axis == "x":
            self.act_cal_y.setChecked(False)
        else:
            self.act_cal_x.setChecked(False)
        self.act_digitize.setChecked(False)
        self.status.showMessage(
            f"Calibrate {axis.upper()}: click two known axis points."  # noqa: E501
        )

    def on_scene_click(self, scene_pos: QtCore.QPointF) -> None:
        if not self.pix_item:
            return
        if not self.pix_item.contains(self.pix_item.mapFromScene(scene_pos)):
            return

        if self.cal_state:
            pts = self.cal_state["points"]
            pts.append(scene_pos)
            self.draw_marker(scene_pos, radius=4)
            if len(pts) == 2:
                axis = self.cal_state["axis"]
                ok1, v1 = self._ask_float(f"Enter {axis.upper()} value for 1st point")
                if not ok1:
                    self._cancel_calibration()
                    return
                ok2, v2 = self._ask_float(f"Enter {axis.upper()} value for 2nd point")
                if not ok2:
                    self._cancel_calibration()
                    return
                p1, p2 = pts
                if axis == "x":
                    x1, x2 = p1.x(), p2.x()
                    if abs(x2 - x1) < 1e-6:
                        QtWidgets.QMessageBox.warning(
                            self, "Bad calibration", "Choose two points with different X."
                        )
                        self._cancel_calibration()
                        return
                    if self.chk_xlog.isChecked():
                        if v1 <= 0 or v2 <= 0:
                            QtWidgets.QMessageBox.warning(
                                self,
                                "Invalid values",
                                "Log scale requires positive values.",
                            )
                            self._cancel_calibration()
                            return
                        V1, V2 = math.log10(v1), math.log10(v2)
                    else:
                        V1, V2 = v1, v2
                    self.ax = (V2 - V1) / (x2 - x1)
                    self.bx = V1 - self.ax * x1
                    mode = "log10" if self.chk_xlog.isChecked() else "linear"
                    self.status.showMessage(
                        f"X calibrated ({mode}): ax={self.ax:.6g}, bx={self.bx:.6g}"
                    )
                    self.act_cal_x.setChecked(False)
                else:
                    y1, y2 = p1.y(), p2.y()
                    if abs(y2 - y1) < 1e-6:
                        QtWidgets.QMessageBox.warning(
                            self, "Bad calibration", "Choose two points with different Y."
                        )
                        self._cancel_calibration()
                        return
                    if self.chk_ylog.isChecked():
                        if v1 <= 0 or v2 <= 0:
                            QtWidgets.QMessageBox.warning(
                                self,
                                "Invalid values",
                                "Log scale requires positive values.",
                            )
                            self._cancel_calibration()
                            return
                        V1, V2 = math.log10(v1), math.log10(v2)
                    else:
                        V1, V2 = v1, v2
                    self.ay = (V2 - V1) / (y2 - y1)
                    self.by = V1 - self.ay * y1
                    mode = "log10" if self.chk_ylog.isChecked() else "linear"
                    self.status.showMessage(
                        f"Y calibrated ({mode}): ay={self.ay:.6g}, by={self.by:.6g}"
                    )
                    self.act_cal_y.setChecked(False)
                self.cal_state = None
            return

        if self.act_digitize.isChecked():
            ok, X, Y = self.pixel_to_data(scene_pos.x(), scene_pos.y())
            if not ok:
                QtWidgets.QMessageBox.information(
                    self, "Not calibrated", "Calibrate both X and Y first."
                )
                return
            self.add_point(X, Y, scene_pos)

    def _ask_float(self, prompt: str) -> tuple[bool, float]:
        val, ok = QtWidgets.QInputDialog.getDouble(
            self, "Calibration", prompt, 0.0, -1e100, 1e100, 6
        )
        return ok, val

    def _cancel_calibration(self) -> None:
        self.cal_state = None
        self.act_cal_x.setChecked(False)
        self.act_cal_y.setChecked(False)

    def pixel_to_data(self, x_px: float, y_px: float) -> tuple[bool, float, float]:
        if None in (self.ax, self.bx, self.ay, self.by):
            return False, 0.0, 0.0
        x_val = self.ax * x_px + self.bx
        y_val = self.ay * y_px + self.by
        if self.chk_xlog.isChecked():
            x_val = 10 ** x_val
        if self.chk_ylog.isChecked():
            y_val = 10 ** y_val
        return True, x_val, y_val

    # ------------------------------------------------------------------
    # Points table / markers
    # ------------------------------------------------------------------
    def add_point(self, X: float, Y: float, scene_pos: QtCore.QPointF) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"{X:.6g}"))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{Y:.6g}"))
        self.draw_marker(scene_pos)
        self.status.showMessage(f"Point {row + 1}: X={X:.6g}, Y={Y:.6g}")

    def draw_marker(self, scene_pos: QtCore.QPointF, radius: Optional[int] = None) -> None:
        r = radius or self.point_radius
        item = QtWidgets.QGraphicsEllipseItem(scene_pos.x() - r, scene_pos.y() - r, 2 * r, 2 * r)
        item.setPen(self.point_pen)
        item.setBrush(self.point_brush)
        item.setZValue(10)
        self.scene.addItem(item)
        self.marker_items.append(item)

    def clear_points(self) -> None:
        self.table.setRowCount(0)
        for it in self.marker_items:
            self.scene.removeItem(it)
        self.marker_items.clear()
        self.status.showMessage("Cleared points.")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_csv(self) -> None:
        if self.table.rowCount() == 0:
            QtWidgets.QMessageBox.information(
                self, "Nothing to export", "Digitize some points first."
            )
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export CSV", "points.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("X,Y\n")
                for r in range(self.table.rowCount()):
                    x = self.table.item(r, 0).text()
                    y = self.table.item(r, 1).text()
                    f.write(f"{x},{y}\n")
            self.status.showMessage(f"Exported to {path}")
        except Exception as exc:  # pragma: no cover - basic error path
            QtWidgets.QMessageBox.warning(self, "Export failed", str(exc))


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Digitize points from a plot image.")
    parser.add_argument("image", nargs="?", help="Image file to open")
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication(sys.argv)
    apply_dark_palette(app)
    win = Digitizer()
    if args.image:
        win.load_image(args.image)
    win.show()
    if os.environ.get("HH_LAUNCHER"):
        QtCore.QTimer.singleShot(0, lambda: print("LAUNCHED", flush=True))
    app.exec_()


if __name__ == "__main__":  # pragma: no cover - manual launch
    main()
