import pandas as pd
import pytest
import types
import sys

import hh_tools.compare_hydrographs as ch


def test_compare_hydrographs_basic(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=5, freq="H")
    obs = pd.DataFrame({"Datetime": t, "Observed": [1, 2, 3, 4, 5]})
    obs_csv = tmp_path / "obs.csv"
    obs.to_csv(obs_csv, index=False)

    def fake_extract(_outfile, _item_type, _element_id, _param):
        return pd.DataFrame({"Datetime": t, "value": [1.1, 1.9, 3.1, 3.9, 5.2]})

    monkeypatch.setattr(ch, "extract_swmm_series", fake_extract)

    plot_path = tmp_path / "plot.png"
    summary_path = tmp_path / "summary.csv"
    code = ch.main([
        "model.out",
        str(obs_csv),
        "J1",
        str(plot_path),
        "--summary",
        str(summary_path),
    ])
    assert code == 0
    assert plot_path.exists()
    summary = pd.read_csv(summary_path)
    nse = summary.loc[summary["metric"] == "nse", "value"].iloc[0]
    rmse = summary.loc[summary["metric"] == "rmse", "value"].iloc[0]
    vol_err = summary.loc[summary["metric"] == "total_volume_error", "value"].iloc[0]
    assert nse == pytest.approx(0.992, rel=1e-3)
    assert rmse == pytest.approx(0.1265, rel=1e-3)
    assert vol_err == pytest.approx(0.0133333, rel=1e-3)


def test_compare_hydrographs_tsf(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=5, freq="H")
    obs = pd.DataFrame({"Date/Time": t, "Flow": [1, 2, 3, 4, 5]})
    obs_tsf = tmp_path / "obs.tsf"
    data = obs.to_csv(sep="\t", index=False, header=False, date_format="%m/%d/%Y %I:%M:%S %p")
    with open(obs_tsf, "w", encoding="utf-8") as f:
        f.write("IDs:\tJ1\n")
        f.write("Date/Time\tFlow\n")
        f.write("M/d/yyyy\tmgd\n")
        f.write(data)

    def fake_extract(_outfile, _item_type, _element_id, _param):
        return pd.DataFrame({"Datetime": t, "value": [1.1, 1.9, 3.1, 3.9, 5.2]})

    monkeypatch.setattr(ch, "extract_swmm_series", fake_extract)

    plot_path = tmp_path / "plot.png"
    summary_path = tmp_path / "summary.csv"
    code = ch.main([
        "model.out",
        str(obs_tsf),
        "J1",
        str(plot_path),
        "--summary",
        str(summary_path),
    ])
    assert code == 0
    summary = pd.read_csv(summary_path)
    nse = summary.loc[summary["metric"] == "nse", "value"].iloc[0]
    vol_err = summary.loc[summary["metric"] == "total_volume_error", "value"].iloc[0]
    assert nse == pytest.approx(0.992, rel=1e-3)
    assert vol_err == pytest.approx(0.0133333, rel=1e-3)



def test_compare_hydrographs_multi_time_cols(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=5, freq="H")
    obs = pd.DataFrame(
        {
            "Year": t.year,
            "Month": t.month,
            "Day": t.day,
            "Hour": t.hour,
            "Minute": t.minute,
            "Observed": [1, 2, 3, 4, 5],
        }
    )
    obs_csv = tmp_path / "obs_multi.csv"
    obs.to_csv(obs_csv, index=False)

    def fake_extract(_outfile, _item_type, _element_id, _param):
        return pd.DataFrame({"Datetime": t, "value": [1.1, 1.9, 3.1, 3.9, 5.2]})

    monkeypatch.setattr(ch, "extract_swmm_series", fake_extract)

    plot_path = tmp_path / "plot.png"
    summary_path = tmp_path / "summary.csv"
    code = ch.main(
        [
            "model.out",
            str(obs_csv),
            "J1",
            str(plot_path),
            "--summary",
            str(summary_path),
            "--obs-time-col",
            "Year,Month,Day,Hour,Minute",
        ]
    )
    assert code == 0
    summary = pd.read_csv(summary_path)
    nse = summary.loc[summary["metric"] == "nse", "value"].iloc[0]
    vol_err = summary.loc[summary["metric"] == "total_volume_error", "value"].iloc[0]
    assert nse == pytest.approx(0.992, rel=1e-3)
    assert vol_err == pytest.approx(0.0133333, rel=1e-3)

def test_compare_hydrographs_header_variations(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=5, freq="H")
    obs = pd.DataFrame(
        {
            "datetime": t,
            "Flow_mgd": [1, 2, 3, 4, 5],
            "Velocity_fps": [0, 0, 0, 0, 0],
        }
    )
    obs_csv = tmp_path / "obs.csv"

    obs.to_csv(obs_csv, index=False)

    def fake_extract(_outfile, _item_type, _element_id, _param):
        return pd.DataFrame({"Datetime": t, "value": [1.1, 1.9, 3.1, 3.9, 5.2]})

    monkeypatch.setattr(ch, "extract_swmm_series", fake_extract)

    plot_path = tmp_path / "plot.png"
    summary_path = tmp_path / "summary.csv"
    code = ch.main([
        "model.out",
        str(obs_csv),
        "J1",
        str(plot_path),
        "--summary",
        str(summary_path),
    ])
    assert code == 0
    summary = pd.read_csv(summary_path)
    nse = summary.loc[summary["metric"] == "nse", "value"].iloc[0]
    vol_err = summary.loc[summary["metric"] == "total_volume_error", "value"].iloc[0]
    assert nse == pytest.approx(0.992, rel=1e-3)
    assert vol_err == pytest.approx(0.0133333, rel=1e-3)


def test_compare_hydrographs_tsf_header_variations(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=5, freq="H")
    obs = pd.DataFrame({"Date/Time": t, "Flow_mgd": [1, 2, 3, 4, 5]})
    obs_tsf = tmp_path / "obs.tsf"
    data = obs.to_csv(
        sep="\t", index=False, header=False, date_format="%m/%d/%Y %I:%M:%S %p"
    )
    with open(obs_tsf, "w", encoding="utf-8") as f:
        f.write("IDs:\tJ1\n")
        f.write("Date/Time\tFlow_mgd\n")
        f.write("M/d/yyyy\tmgd\n")
        f.write(data)

    def fake_extract(_outfile, _item_type, _element_id, _param):
        return pd.DataFrame({"Datetime": t, "value": [1.1, 1.9, 3.1, 3.9, 5.2]})

    monkeypatch.setattr(ch, "extract_swmm_series", fake_extract)

    plot_path = tmp_path / "plot.png"
    summary_path = tmp_path / "summary.csv"
    code = ch.main([
        "model.out",
        str(obs_tsf),
        "J1",
        str(plot_path),
        "--summary",
        str(summary_path),
    ])

    assert code == 0
    summary = pd.read_csv(summary_path)
    nse = summary.loc[summary["metric"] == "nse", "value"].iloc[0]
    vol_err = summary.loc[summary["metric"] == "total_volume_error", "value"].iloc[0]
    assert nse == pytest.approx(0.992, rel=1e-3)
    assert vol_err == pytest.approx(0.0133333, rel=1e-3)


def test_compare_hydrographs_creates_pptx(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=5, freq="H")
    obs = pd.DataFrame({"Datetime": t, "Observed": [1, 2, 3, 4, 5]})
    obs_csv = tmp_path / "obs.csv"
    obs.to_csv(obs_csv, index=False)

    def fake_extract(_outfile, _item_type, _element_id, _param):
        return pd.DataFrame({"Datetime": t, "value": [1.1, 1.9, 3.1, 3.9, 5.2]})

    monkeypatch.setattr(ch, "extract_swmm_series", fake_extract)

    captured = {}

    class DummyShapes:
        def add_picture(self, path, *args, **kwargs):
            captured["img"] = path

    class DummySlides(list):
        def add_slide(self, _layout):
            slide = types.SimpleNamespace(shapes=DummyShapes())
            self.append(slide)
            return slide

    class DummyPresentation:
        slide_layouts = [None] * 7

        def __init__(self, *args, **kwargs):
            self.slides = DummySlides()

        def save(self, path):
            captured["save_path"] = path

    monkeypatch.setitem(sys.modules, "pptx", types.SimpleNamespace(Presentation=DummyPresentation))
    monkeypatch.setitem(sys.modules, "pptx.util", types.SimpleNamespace(Inches=lambda x: x))

    plot_path = tmp_path / "plot.png"
    pptx_path = tmp_path / "slides.pptx"
    code = ch.main([
        "model.out",
        str(obs_csv),
        "J1",
        str(plot_path),
        "--pptx",
        str(pptx_path),
    ])
    assert code == 0
    assert captured["save_path"] == str(pptx_path)
    assert captured["img"] == str(plot_path)
