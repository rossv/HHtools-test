"""Centralized help messages for GUI modules.

This module keeps short help texts for each GUI front-end so that
documentation strings only need to be maintained in one place.  The
``show_help`` helper displays the message for a given key using a simple
``QMessageBox``.
"""

from __future__ import annotations

from PyQt5 import QtWidgets

# Mapping of short usage strings for each GUI.  The keys roughly match the
# module names without the ``_gui`` suffix.  The messages intentionally stay
# brief and point users towards the correct action within each tool.
HELP_MESSAGES = {
    "extract_timeseries": "Add .out files, choose IDs and parameters, then run to export timeseries.",
    "sensitivity": "Provide base INP, parameter file and metrics, then Run to start the analysis.",
    "summarize_outfiles": "Select SWMM .out files and summarise chosen IDs and parameters to a CSV report.",
    "inp_diff": "Pick two INP files to compare; differing values appear in the table.",
    "compare_outfiles": "Select two .out files, discover IDs/parameters and run to compare results.",
    "calibrate_model": "Choose base INP, bounds and observed data then run model calibration.",
    "batch_runner": "Add multiple .inp files to the table and run them sequentially.",
    "validate_inp": "Add INP files and run to check for common errors and warnings.",
    "event_extractor": "Select input CSV, threshold and minimum duration then extract events.",
    "plot_digitizer": "Open an image, calibrate axes, then click to record points and export to CSV.",
    "resample_timeseries": "Select input series, new timestep and format then resample.",
}


def show_help(key: str, parent: QtWidgets.QWidget | None = None) -> None:
    """Display a help dialog for the given GUI ``key``.

    Parameters
    ----------
    key:
        Identifier for the GUI, typically the module name without ``_gui``.
    parent:
        Optional parent widget for the message box.
    """

    message = HELP_MESSAGES.get(key, "Documentation not available.")
    QtWidgets.QMessageBox.information(parent, "Help", message)


__all__ = ["show_help", "HELP_MESSAGES"]

