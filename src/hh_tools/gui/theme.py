# theme.py
from PyQt5 import QtCore, QtGui, QtWidgets

def apply_dark_palette(app: QtWidgets.QApplication) -> None:
    """Fusion dark palette with sane contrasts."""
    app.setStyle("Fusion")
    app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    palette = QtGui.QPalette()

    window      = QtGui.QColor(0x2F, 0x2F, 0x2F)
    base        = QtGui.QColor(0x33, 0x33, 0x33)
    alt_base    = QtGui.QColor(0x2B, 0x2B, 0x2B)
    button      = alt_base
    text        = QtGui.QColor(230, 230, 230)
    text_dim    = QtGui.QColor(150, 150, 150)
    tooltip_bg  = QtGui.QColor(70, 70, 70)
    tooltip_fg  = QtGui.QColor(240, 240, 240)
    link        = QtGui.QColor(0x2A, 0x82, 0xDA)

    palette.setColor(QtGui.QPalette.Window, window)
    palette.setColor(QtGui.QPalette.WindowText, text)
    palette.setColor(QtGui.QPalette.Base, base)
    palette.setColor(QtGui.QPalette.AlternateBase, alt_base)
    palette.setColor(QtGui.QPalette.ToolTipBase, tooltip_bg)
    palette.setColor(QtGui.QPalette.ToolTipText, tooltip_fg)
    palette.setColor(QtGui.QPalette.Text, text)
    palette.setColor(QtGui.QPalette.Button, button)
    palette.setColor(QtGui.QPalette.ButtonText, text)
    palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    palette.setColor(QtGui.QPalette.Link, link)
    palette.setColor(QtGui.QPalette.Highlight, link)
    palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)

    # Disabled state
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, text_dim)
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text,       text_dim)
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, text_dim)
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Highlight,  QtGui.QColor(70, 70, 70))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.HighlightedText, QtGui.QColor(180, 180, 180))

    app.setPalette(palette)


def apply_global_styles(app: QtWidgets.QApplication) -> None:
    """App-wide QSS. Key bit: don't add padding to card icon buttons."""
    qss = """
    * { font-family: Segoe UI, Roboto, "Helvetica Neue", Arial; font-size: 10.5pt; }
    QMainWindow { background: #2f2f2f; }

    /* ---- Toolbar ---- */
    QToolBar { background: #2b2b2b; border: none; padding: 6px; }
    QToolBar QToolButton { padding: 6px 10px; border-radius: 8px; }
    QToolBar QToolButton:hover  { background: rgba(255,255,255,0.06); }
    QToolBar QToolButton:pressed{ background: rgba(42,130,218,0.25); }

    /* ---- Header ---- */
    #header { color: #ffffff; font-size: 22pt; font-weight: 750; padding: 6px 2px 2px 2px; }

    /* ---- Search ---- */
    QLineEdit {
        background: #3a3a3a; border: 1px solid #4a4a4a; border-radius: 10px; padding: 8px 10px;
        color: #f0f0f0;
        selection-background-color: #2A82DA; selection-color: white;
    }
    QLineEdit:focus { border: 1px solid #2A82DA; background: #3c3c3c; }

    /* ---- Cards ---- */
    QFrame#card {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a3a3a, stop:1 #343434);
        border: 1px solid #4b4b4b; border-radius: 16px;
    }
    QFrame#card:hover { border: 1px solid #2A82DA; background: #3c3c3c; }
    QFrame#card:focus { border: 2px solid #2A82DA; }

    #pinBadge { color: #FFD166; font-size: 13pt; margin-right: 2px; }

    /* Icon button inside a card:
       - zero padding so the icon is centered on first paint (no jump)
       - keep hover/pressed backgrounds for feedback
    */
    QFrame#card QToolButton {
        padding: 0px; margin: 0px; border: none; border-radius: 12px;
        background: transparent;
    }
    QFrame#card QToolButton:hover  { background: rgba(255,255,255,0.07); }
    QFrame#card QToolButton:pressed{ background: rgba(42,130,218,0.35); }

    /* Text inside cards */
    QFrame#card QLabel { color: #eaeaea; }

    /* Scroll/status */
    QScrollArea { border: none; background: transparent; }
    QStatusBar { background: #2b2b2b; border-top: 1px solid #444; color: #dcdcdc; }
    """
    app.setStyleSheet(qss)
