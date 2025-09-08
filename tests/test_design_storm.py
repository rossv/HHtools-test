import numpy as np
import pytest
import logging
import requests
import sys
import types
from hh_tools import design_storm
from hh_tools.design_storm import (
    build_storm,
    beta_curve,
    write_pcswmm_dat,
    save_preset,
    load_preset,
)

def test_build_storm_cumulative_depth():
    df = build_storm(depth=2.0, duration_hr=1.0, timestep_min=15, distribution='scs_type_ii', peak=0.5)
    assert df['cumulative_in'].iloc[-1] == pytest.approx(2.0)
    assert len(df) == 4

def test_beta_curve_normalized_and_peak():
    n = 10
    pdf = beta_curve(n, 2.0, 5.0, 3)
    assert pdf.sum() == pytest.approx(1.0)
    assert int(np.argmax(pdf)) == 3


def test_write_pcswmm_dat(tmp_path):
    df = build_storm(
        depth=0.5, duration_hr=1.0, timestep_min=15, distribution="scs_type_ii", peak=0.5
    )
    path = tmp_path / "storm.dat"
    write_pcswmm_dat(df, 15, path)
    lines = path.read_text().splitlines()
    assert lines[0].startswith(";Rainfall")
    assert lines[1].startswith(";PCSWMM")
    assert lines[2].startswith("System\t2003\t1\t1")
    assert len(lines) == len(df) + 2


def test_fetch_noaa_table_request_exception(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(design_storm, "_fetch_noaa_csv", boom)
    monkeypatch.setattr(design_storm, "pfdf_atlas14", None)
    with caplog.at_level(logging.ERROR):
        result = design_storm.fetch_noaa_table(0.0, 0.0)
    assert result is None
    assert "NOAA table download failed" in caplog.text


def test_main_creates_pptx(tmp_path, monkeypatch):
    hyeto = tmp_path / "hyetograph.png"
    pptx_path = tmp_path / "out.pptx"

    def fake_plot(_df, path):
        path.write_text("img")

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

    monkeypatch.setattr(design_storm, "plot_hyetograph", fake_plot)
    monkeypatch.setitem(sys.modules, "pptx", types.SimpleNamespace(Presentation=DummyPresentation))
    monkeypatch.setitem(sys.modules, "pptx.util", types.SimpleNamespace(Inches=lambda x: x))

    code = design_storm.main([
        "--duration",
        "1",
        "--depth",
        "1",
        "--time-step",
        "1",
        "--out-hyetograph",
        str(hyeto),
        "--pptx",
        str(pptx_path),
    ])
    assert code == 0
    assert captured["save_path"] == str(pptx_path)
    assert captured["img"] == str(hyeto)


def test_user_distribution_from_csv(tmp_path):
    csv = tmp_path / "curve.csv"
    csv.write_text("t,c\n0,0\n1,1\n")
    df = build_storm(
        depth=1.0,
        duration_hr=1.0,
        timestep_min=30,
        distribution="user",
        custom_curve_path=csv,
    )
    assert df["cumulative_in"].iloc[-1] == pytest.approx(1.0)
    assert len(df) == 2


def test_save_and_load_preset(tmp_path):
    preset = tmp_path / "preset.json"
    args = types.SimpleNamespace(
        location="loc",
        duration=1.0,
        return_period=10.0,
        depth=1.0,
        time_step=5.0,
        distribution="scs_type_ii",
        peak=None,
        custom_curve=None,
        start_datetime=None,
        gauge_name="G",
        export_type="intensity",
    )
    save_preset(args, preset)
    empty = types.SimpleNamespace(
        location=None,
        duration=None,
        return_period=None,
        depth=None,
        time_step=None,
        distribution=None,
        peak=None,
        custom_curve=None,
        start_datetime=None,
        gauge_name=None,
        export_type=None,
    )
    load_preset(preset, empty)
    assert empty.duration == 1.0
    assert empty.gauge_name == "G"


def test_import_without_requests(monkeypatch):
    import builtins
    import importlib
    import sys

    sys.modules.pop("hh_tools.design_storm", None)
    sys.modules.pop("requests", None)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "requests":
            raise ModuleNotFoundError
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    ds = importlib.import_module("hh_tools.design_storm")
    assert ds.requests is None

    df = ds.build_storm(depth=1.0, duration_hr=1.0, timestep_min=15, distribution="scs_type_ii", peak=0.5)
    assert df["cumulative_in"].iloc[-1] == pytest.approx(1.0)

