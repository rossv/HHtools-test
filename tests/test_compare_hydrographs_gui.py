import pandas as pd
import pandas as pd
import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5 import QtCore, QtWidgets

from hh_tools.gui.compare_hydrographs_gui import CompareHydrographsWindow


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.quit()


def test_time_columns_excluded_from_mapping(qapp, tmp_path):
    df = pd.DataFrame(
        {
            "Year": [2020],
            "Month": [1],
            "Day": [1],
            "Hour": [0],
            "Minute": [0],
            "Flow_mgd": [1.0],
            "Depth_in": [0.1],
        }
    )
    csv = tmp_path / "obs.csv"
    df.to_csv(csv, index=False)

    win = CompareHydrographsWindow()
    win.obs_edit.setText(str(csv))
    qapp.processEvents()

    selected = {item.text() for item in win.time_list.selectedItems()}
    assert {"Year", "Month", "Day", "Hour", "Minute"}.issubset(selected)

    for col in ["Year", "Month", "Day", "Hour", "Minute"]:
        assert col not in win.available_columns

    mapped_cols = [c.currentText() for (_row, c, _p) in win.mapping_rows]
    assert set(mapped_cols) == {"Flow_mgd", "Depth_in"}

    options = [
        win.mapping_rows[0][1].itemText(i)
        for i in range(win.mapping_rows[0][1].count())
    ]
    for col in ["Year", "Month", "Day", "Hour", "Minute"]:
        assert col not in options


def test_process_error_resets_ui(qapp, tmp_path, monkeypatch):
    # Create minimal observed and model files
    obs = pd.DataFrame({"Datetime": ["2020-01-01"], "Value": [1]})
    obs_csv = tmp_path / "obs.csv"
    obs.to_csv(obs_csv, index=False)
    model_out = tmp_path / "model.out"
    model_out.write_text("")
    plot = tmp_path / "plot.png"

    win = CompareHydrographsWindow()
    win.out_edit.setText(str(model_out))
    win.obs_edit.setText(str(obs_csv))
    win.plot_edit.setText(str(plot))
    win.id_combo.setEditText("J1")
    qapp.processEvents()

    # Force QProcess to emit a FailedToStart error
    monkeypatch.setattr(
        win.process,
        "start",
        lambda *_args, **_kwargs: win.process.errorOccurred.emit(
            QtCore.QProcess.ProcessError.FailedToStart
        ),
    )

    win._run()
    qapp.processEvents()

    assert win.run_btn.isEnabled()
    assert not win.progress.isVisible()


def test_run_includes_pptx_arg(qapp, tmp_path, monkeypatch):
    obs = pd.DataFrame({"Datetime": ["2020-01-01"], "Observed": [1.0]})
    obs_csv = tmp_path / "obs.csv"
    obs.to_csv(obs_csv, index=False)
    model_out = tmp_path / "model.out"
    model_out.write_text("")
    plot = tmp_path / "plot.png"
    pptx = tmp_path / "slides.pptx"

    win = CompareHydrographsWindow()
    win.out_edit.setText(str(model_out))
    win.obs_edit.setText(str(obs_csv))
    win.plot_edit.setText(str(plot))
    win.pptx_edit.setText(str(pptx))
    win.id_combo.setEditText("J1")
    qapp.processEvents()

    captured = {}

    def fake_start_next_run():
        captured["args"] = win.pending_runs.copy()

    monkeypatch.setattr(win, "_start_next_run", fake_start_next_run)
    win._run()
    args = captured["args"][0]
    assert "--pptx" in args
    assert args[args.index("--pptx") + 1] == str(pptx)
