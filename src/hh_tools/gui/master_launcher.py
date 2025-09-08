#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H&H Tools Launcher — centered icons, pressed color, spinner, zero press-shift.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------------------
# Ensure runtime dependencies are available
# --------------------------------------------------------------------------------------
PKG_ROOT = Path(__file__).resolve().parents[2]


def _ensure_dependencies() -> None:
    """Install missing project dependencies at runtime.

    The launcher may be executed in an environment where required libraries
    (e.g. ``requests``) are missing.  To provide a smoother user experience we
    parse ``pyproject.toml`` for declared dependencies and invoke ``pip`` to
    install any that are not already importable.  Errors are ignored so that
    the launcher can still display a helpful message if installation fails.
    """

    try:
        import tomllib
    except Exception:
        return

    pyproject = PKG_ROOT / "pyproject.toml"
    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        deps = data.get("project", {}).get("dependencies", [])
    except Exception:
        deps = []

    missing: List[str] = []
    for dep in deps:
        pkg = dep.split(";")[0].split("[")[0].split("==")[0].split(">=")[0].strip()
        if importlib.util.find_spec(pkg) is None:
            missing.append(dep)

    if missing:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        except Exception:
            pass


_ensure_dependencies()

from PyQt5 import QtCore, QtGui, QtWidgets

# ---- Repo/package root
if __package__ is None:
    sys.path.append(str(PKG_ROOT))

from hh_tools.gui.theme import apply_dark_palette, apply_global_styles

ICON_DIR = Path(__file__).with_name("icons")

# Optional search keywords
TOOL_KEYWORDS: Dict[str, List[str]] = {
    "batch_runner": ["batch", "automation", "run"],
    "compare_hydrographs": ["compare", "hydrograph", "hydrographs"],
    "compare_outfiles": ["compare", "outfile", "results"],
    "design_storm": ["design", "storm", "rain"],
    "download_rainfall": ["download", "rain", "rainfall"],
    "download_streamflow": ["download", "streamflow", "flow"],
    "extract_timeseries": ["extract", "time series", "rain", "flow"],
    "review_flow_data": ["review", "flow", "data"],
    "sensitivity": ["sensitivity", "analysis"],
    "summarize_outfiles": ["summarize", "outfile", "results"],
    "validate_inp": ["validate", "inp", "input"],
    "event_extractor": ["event", "extract", "rain", "flow"],
    "inp_diff": ["inp", "diff", "compare", "input"],
    "calibrate_model": ["calibrate", "parameter", "optimization"],
    "plot_digitizer": ["digitize", "plot", "image"],
    "flow_decomp": ["flow", "decompose", "gwi", "wwf"],
}

# Optional category grouping
TOOL_CATEGORIES: Dict[str, str] = {
    "download_rainfall": "Rainfall",
    "design_storm": "Rainfall",
    "event_extractor": "Rainfall",
    "review_flow_data": "Rainfall",
    "compare_hydrographs": "Analysis",
    "compare_outfiles": "Analysis",
    "extract_timeseries": "Analysis",
    "summarize_outfiles": "Analysis",
    "sensitivity": "Analysis",
    "calibrate_model": "Analysis",
    "flow_decomp": "Analysis",
    "batch_runner": "Utilities",
    "download_streamflow": "Utilities",
    "validate_inp": "Utilities",
    "inp_diff": "Utilities",
    "plot_digitizer": "Utilities",
}


# --------------------------------------------------------------------------------------
# Launch child GUI
# --------------------------------------------------------------------------------------
def _launch_gui(module: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PKG_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.Popen([sys.executable, "-m", module], env=env)


# --------------------------------------------------------------------------------------
# Discover hh_tools.gui.* _gui modules
# --------------------------------------------------------------------------------------
def _module_description(mod) -> str:
    """Return a short description for *mod*.

    Preference is given to a ``DESCRIPTION`` attribute, otherwise the first
    sentence of the module's docstring is used.
    """

    desc = getattr(mod, "DESCRIPTION", "")
    if not desc:
        doc = mod.__doc__ or ""
        desc = doc.strip().splitlines()[0] if doc else ""
    return desc


def _discover_tools() -> List[Tuple[str, str, str, str]]:
    """Return a list of available GUI tools.

    Each entry is ``(label, module, description, category)``.
    """

    results: List[Tuple[str, str, str, str]] = []
    try:
        import hh_tools.gui as rootpkg  # type: ignore
    except Exception:
        return results

    prefix = rootpkg.__name__ + "."
    for _, modname, ispkg in pkgutil.walk_packages(rootpkg.__path__, prefix):
        if ispkg or not modname.endswith("_gui"):
            continue
        base = modname.split(".")[-1].replace("_gui", "")
        words = base.replace("_", " ").split()
        label = " ".join(w.capitalize() for w in words)
        try:
            mod = importlib.import_module(modname)
            desc = _module_description(mod)
        except Exception:
            desc = ""
        category = TOOL_CATEGORIES.get(base, "Utilities")
        results.append((label, modname, desc, category))

    results.sort(key=lambda p: p[0].lower())
    return results


# --------------------------------------------------------------------------------------
# Flow layout (Qt example port)
# --------------------------------------------------------------------------------------
class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=8, hspacing=12, vspacing=12):
        super().__init__(parent)
        self._items: List[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        for item in self._items:
            spaceX = self._hspace
            spaceY = self._vspace
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()


# --------------------------------------------------------------------------------------
# Spinner (simple painter-based)
# --------------------------------------------------------------------------------------
class Spinner(QtWidgets.QWidget):
    def __init__(self, parent=None, radius=9, line_width=2, lines=12, interval_ms=80):
        super().__init__(parent)
        self._radius = radius
        self._line_width = line_width
        self._lines = lines
        self._angle = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(interval_ms)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(radius * 2 + 4, radius * 2 + 4)
        self.hide()

    def start(self):
        if not self.isVisible():
            self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._angle = (self._angle + (360 // self._lines)) % 360
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.translate(self.rect().center())
        p.rotate(self._angle)
        for i in range(self._lines):
            alpha = int(255 * (i + 1) / self._lines)
            color = QtGui.QColor(255, 255, 255, alpha)
            pen = QtGui.QPen(
                color, self._line_width, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap
            )
            p.setPen(pen)
            p.drawLine(0, -self._radius, 0, -self._radius // 2)
            p.rotate(360 / self._lines)


# --------------------------------------------------------------------------------------
# IconButton — custom, no press-offset, paints its own background, DPR-safe icon draw
# --------------------------------------------------------------------------------------
class IconButton(QtWidgets.QWidget):
    clicked = QtCore.pyqtSignal()

    def __init__(
        self, icon: QtGui.QIcon, size: QtCore.QSize, radius: int = 12, parent=None
    ):
        super().__init__(parent)
        self._icon = icon
        self._size = size
        self._radius = radius
        self._hover = False
        self._pressed = False
        self._flash = 0.0
        self.setFixedSize(self._size)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self._flashAnim = QtCore.QPropertyAnimation(self, b"flash", self)
        self._flashAnim.setDuration(140)
        self._flashAnim.setStartValue(1.0)
        self._flashAnim.setEndValue(0.0)
        self._flashAnim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

    @QtCore.pyqtProperty(float)
    def flash(self) -> float:
        return self._flash

    @flash.setter
    def flash(self, v: float) -> None:
        self._flash = float(v)
        self.update()

    def flash_once(self):
        self._flashAnim.stop()
        self.flash = 1.0
        self._flashAnim.start()

    def setIcon(self, icon: QtGui.QIcon) -> None:
        self._icon = icon
        self.update()

    def setIconSize(self, size: QtCore.QSize) -> None:
        self._size = size
        self.setFixedSize(size)
        self.update()

    # States
    def enterEvent(self, _):
        self._hover = True
        self.update()

    def leaveEvent(self, _):
        self._hover = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, ev):
        if self._pressed and ev.button() == QtCore.Qt.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(ev.pos()):
                self.clicked.emit()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # Hover/pressed background (no geometry nudge)
        if self._pressed:
            bg = QtGui.QColor(42, 130, 218, 90)  # pressed tint
        elif self._hover:
            bg = QtGui.QColor(255, 255, 255, 18)  # hover tint
        else:
            bg = QtCore.Qt.transparent

        if bg != QtCore.Qt.transparent or self._flash > 0.001:
            path = QtGui.QPainterPath()
            rectf = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            path.addRoundedRect(rectf, float(self._radius), float(self._radius))
            if bg != QtCore.Qt.transparent:
                p.fillPath(path, bg)
            if self._flash > 0.001:
                # brief press flash
                flashc = QtGui.QColor(42, 130, 218, int(120 * self._flash))
                p.fillPath(path, flashc)

        # Icon — DPR-safe center draw (no off-by-one drift)
        self._icon.paint(
            p,
            self.rect(),
            QtCore.Qt.AlignCenter,
            mode=QtGui.QIcon.Normal,
            state=QtGui.QIcon.Off,
        )


# --------------------------------------------------------------------------------------
# Tool Card
# --------------------------------------------------------------------------------------
class ToolCard(QtWidgets.QFrame):
    launched = QtCore.pyqtSignal(object)
    pinToggled = QtCore.pyqtSignal(str, bool)

    def __init__(
        self,
        label: str,
        module: str,
        icon: QtGui.QIcon,
        keywords: Optional[List[str]] = None,
        pinned: bool = False,
        description: str = "",
        category: str = "",
    ):
        super().__init__()
        self.label = label
        self.module = module
        self.pinned = pinned
        self.keywords = keywords or []
        self.description = description
        self.category = category
        self.setObjectName("card")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        if self.description:
            self.setToolTip(self.description)

        # Drop shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QtGui.QColor(0, 0, 0, 140))
        self.setGraphicsEffect(shadow)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Pin badge
        self.pinBadge = QtWidgets.QLabel("📌", self)
        self.pinBadge.setObjectName("pinBadge")
        self.pinBadge.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.pinBadge.setVisible(self.pinned)
        layout.addWidget(self.pinBadge)

        # --- Icon holder (no layouts shifting on click) ---
        self.iconHolder = QtWidgets.QFrame(self)
        self.iconHolder.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.iconHolder.setFixedSize(72, 72)

        self.iconBtn = IconButton(
            icon, QtCore.QSize(72, 72), radius=12, parent=self.iconHolder
        )
        self.iconBtn.setGeometry(0, 0, 72, 72)

        # Spinner absolute-positioned (no layout recompute on show)
        self.spinner = Spinner(
            self.iconHolder, radius=9, line_width=2, lines=12, interval_ms=80
        )
        self.spinner.move(
            self.iconHolder.width() - self.spinner.width(),
            self.iconHolder.height() - self.spinner.height(),
        )

        layout.addWidget(self.iconHolder, alignment=QtCore.Qt.AlignHCenter)

        # Title
        self.text = QtWidgets.QLabel(self.label, self)
        self.text.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        self.text.setWordWrap(True)
        layout.addWidget(self.text)

        # Signals
        self.iconBtn.clicked.connect(self._launch)

    # Right-click menu
    def contextMenuEvent(self, ev: QtGui.QContextMenuEvent) -> None:
        m = QtWidgets.QMenu(self)
        act_launch = m.addAction("Launch")
        act_help = m.addAction("Help")
        act_pin = m.addAction("Unpin" if self.pinned else "Pin")
        m.addSeparator()
        act_copy = m.addAction("Copy module path")
        act_icons = m.addAction("Show icons folder")
        chosen = m.exec_(ev.globalPos())
        if chosen == act_launch:
            self._launch()
        elif chosen == act_help:
            self._open_help()
        elif chosen == act_pin:
            self.pinned = not self.pinned
            self.pinBadge.setVisible(self.pinned)
            self.pinToggled.emit(self.module, self.pinned)
        elif chosen == act_copy:
            QtWidgets.QApplication.clipboard().setText(self.module)
        elif chosen == act_icons:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(ICON_DIR)))

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        # Clicking anywhere on the card launches too
        if ev.button() == QtCore.Qt.LeftButton and not self.iconBtn.rect().contains(
            self.iconBtn.mapFrom(self, ev.pos())
        ):
            self._launch()
        super().mousePressEvent(ev)

    def _launch(self) -> None:
        # Flash + spinner; no opacity effects (those can cause a 1px “jiggle” on some DPIs)
        self.iconBtn.flash_once()
        self.spinner.start()
        self.launched.emit(self)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(250, 190)

    def _open_help(self) -> None:
        try:
            import importlib
            import pydoc
            import tempfile
            import webbrowser
            from pathlib import Path

            mod = importlib.import_module(self.module)
            doc = pydoc.HTMLDoc().page(
                mod.__name__, pydoc.HTMLDoc().document(mod)
            )
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as fh:
                fh.write(doc)
                temp_path = Path(fh.name)
            webbrowser.open(temp_path.as_uri())
        except Exception as exc:  # pragma: no cover - best effort
            QtWidgets.QMessageBox.warning(
                self,
                "Documentation not available",
                str(exc),
            )


# --------------------------------------------------------------------------------------
# Main Window
# --------------------------------------------------------------------------------------
class LauncherWindow(QtWidgets.QMainWindow):
    ORG = "WadeTrim"
    APP = "HHLauncher"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("H&H Tools Launcher")
        launcher_icon = ICON_DIR / "master_launcher.ico"
        if launcher_icon.exists():
            self.setWindowIcon(QtGui.QIcon(str(launcher_icon)))
        self._procs: Dict[QtCore.QProcess, ToolCard] = {}

        self.settings = QtCore.QSettings(self.ORG, self.APP)
        self.pinned = set(self.settings.value("pinned", [], type=list))

        # Toolbar
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        act_refresh = tb.addAction("Refresh")
        act_refresh.triggered.connect(self._refresh)

        # Header + search
        container = QtWidgets.QWidget(self)
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(10)

        header = QtWidgets.QLabel("H&H Tools", self)
        header.setObjectName("header")
        v.addWidget(header)

        self.search = QtWidgets.QLineEdit(self)
        self.search.setPlaceholderText("Search tools…")
        self.search.textChanged.connect(self._apply_filter)
        v.addWidget(self.search)

        # Cards area
        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        wrap = QtWidgets.QWidget(self.scroll)
        self.container_layout = QtWidgets.QVBoxLayout(wrap)
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        # Tighten vertical space between tool categories
        self.container_layout.setSpacing(12)
        wrap.setLayout(self.container_layout)
        self.scroll.setWidget(wrap)
        v.addWidget(self.scroll, 1)

        # Status
        self.status = self.statusBar()

        self.setCentralWidget(container)

        # Hotkeys
        QtWidgets.QShortcut(QtGui.QKeySequence.Find, self, activated=self._focus_search)
        QtWidgets.QShortcut(QtGui.QKeySequence("/"), self, activated=self._focus_search)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Esc"), self, activated=self._clear_search
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Return"), self, activated=self._launch_first_visible
        )

        # Populate
        self.cards: List[ToolCard] = []
        self._build_cards()

    def _build_cards(self) -> None:
        # Clear existing widgets
        def _clear(layout: QtWidgets.QLayout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    _clear(item.layout())

        _clear(self.container_layout)
        self.cards.clear()

        tools = _discover_tools()

        # Separate pinned tools
        pinned_tools = [t for t in tools if t[1] in self.pinned]
        other_tools = [t for t in tools if t[1] not in self.pinned]

        groups: List[Tuple[str, List[Tuple[str, str, str, str]]]] = []
        if pinned_tools:
            groups.append(("Pinned", pinned_tools))

        by_cat: Dict[str, List[Tuple[str, str, str, str]]] = {}
        for t in other_tools:
            by_cat.setdefault(t[3], []).append(t)
        for cat in sorted(by_cat):
            groups.append((cat, by_cat[cat]))

        for category, items in groups:
            box = QtWidgets.QGroupBox(category, self.scroll.widget())
            flow = FlowLayout(box, margin=8, hspacing=12, vspacing=12)
            box.setLayout(flow)
            self.container_layout.addWidget(box)
            for label, module, desc, cat in sorted(items, key=lambda p: p[0].lower()):
                base_name = module.split(".")[-1].replace("_gui", "")
                icon_path = ICON_DIR / f"{base_name}.ico"
                icon = (
                    QtGui.QIcon(str(icon_path))
                    if icon_path.exists()
                    else self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
                )

                card = ToolCard(
                    label=label,
                    module=module,
                    icon=icon,
                    keywords=TOOL_KEYWORDS.get(base_name, []),
                    pinned=(module in self.pinned),
                    description=desc,
                    category=cat,
                )
                card.launched.connect(self._launch_card)
                card.pinToggled.connect(self._pin_toggled)
                card.setFocusPolicy(QtCore.Qt.StrongFocus)

                flow.addWidget(card)
                self.cards.append(card)

        self.container_layout.addStretch(1)

        self._apply_filter(self.search.text())
        self._update_status(
            len([c for c in self.cards if c.isVisible()]), len(self.cards)
        )

    def _refresh(self) -> None:
        self._build_cards()

    def _apply_filter(self, text: str) -> None:
        q = text.strip().lower()
        visible = 0
        for c in self.cards:
            hay = (
                f"{c.label} {c.module} {' '.join(c.keywords)} {c.description} {c.category}"
            ).lower()
            show = (q in hay) if q else True
            c.setVisible(show)
            visible += int(show)
        self._update_status(visible, len(self.cards))

    def _update_status(self, visible: int, total: int) -> None:
        self.status.showMessage(f"{visible} of {total} tools")

    def _pin_toggled(self, module: str, pinned: bool) -> None:
        if pinned:
            self.pinned.add(module)
        else:
            self.pinned.discard(module)
        self.settings.setValue("pinned", list(self.pinned))
        self._build_cards()

    def _launch_card(self, card: ToolCard) -> None:
        proc = QtCore.QProcess(self)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PKG_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["HH_LAUNCHER"] = "1"
        qenv = QtCore.QProcessEnvironment()
        for k, v in env.items():
            qenv.insert(k, v)
        proc.setProcessEnvironment(qenv)
        proc.setProgram(sys.executable)
        proc.setArguments(["-m", card.module])
        proc.readyReadStandardOutput.connect(self._proc_output)
        proc.readyReadStandardError.connect(self._proc_output)
        proc.errorOccurred.connect(lambda _err, p=proc: self._proc_failed(p))
        proc.finished.connect(lambda _code, _status, p=proc: self._proc_failed(p))
        self._procs[proc] = card
        proc.start()

    def _proc_output(self) -> None:
        proc = self.sender()
        if proc not in self._procs:
            return
        data = (
            bytes(proc.readAllStandardOutput()).decode()
            + bytes(proc.readAllStandardError()).decode()
        )
        if "LAUNCHED" in data:
            self._procs[proc].spinner.stop()
            del self._procs[proc]

    def _proc_failed(self, proc: QtCore.QProcess) -> None:
        card = self._procs.pop(proc, None)
        if card:
            card.spinner.stop()

    def _focus_search(self) -> None:
        self.search.setFocus(QtCore.Qt.ShortcutFocusReason)
        self.search.selectAll()

    def _clear_search(self) -> None:
        self.search.clear()

    def _launch_first_visible(self) -> None:
        for c in self.cards:
            if c.isVisible():
                c._launch()
                return


# --------------------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------------------
def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    launcher_icon = ICON_DIR / "master_launcher.ico"
    if launcher_icon.exists():
        app.setWindowIcon(QtGui.QIcon(str(launcher_icon)))
    apply_dark_palette(app)
    apply_global_styles(app)
    win = LauncherWindow()
    win.resize(1100, 720)
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
