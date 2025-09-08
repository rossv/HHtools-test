import json

import pandas as pd
import pytest

from hh_tools.calibrate_model import calibrate_model, main as cli_main


def test_calibrate_model_adjusts_parameter(tmp_path, monkeypatch):
    base_inp = tmp_path / "base.inp"
    base_inp.write_text("$K1\n")
    bounds = tmp_path / "bounds.json"
    bounds.write_text(json.dumps({"K1": [0.0, 1.0]}))
    observed = tmp_path / "obs.csv"
    pd.DataFrame({"flow": [0.2, 0.4]}).to_csv(observed, index=False)

    def fake_run(inp, params, swmm):
        val = params["K1"]
        return pd.Series([val, val * 2])

    monkeypatch.setattr("hh_tools.calibrate_model._run_swmm", fake_run)

    best, res = calibrate_model(base_inp, bounds, observed, metric="rmse", swmm_exe="swmm5")
    assert best["K1"] == pytest.approx(0.2, rel=1e-2)


def test_cli_parsing_and_output(tmp_path, monkeypatch):
    base_inp = tmp_path / "base.inp"
    base_inp.write_text("$K1\n")
    bounds = tmp_path / "bounds.json"
    bounds.write_text(json.dumps({"K1": [0.0, 1.0]}))
    observed = tmp_path / "obs.csv"
    pd.DataFrame({"flow": [0.2, 0.4]}).to_csv(observed, index=False)
    out = tmp_path / "params.json"

    def fake_run(inp, params, swmm):
        val = params["K1"]
        return pd.Series([val, val * 2])

    monkeypatch.setattr("hh_tools.calibrate_model._run_swmm", fake_run)

    cli_main(
        [
            str(base_inp),
            "--bounds",
            str(bounds),
            "--observed",
            str(observed),
            "--metric",
            "rmse",
            "--output",
            str(out),
            "--swmm",
            "swmm5",
        ]
    )
    result = json.loads(out.read_text())
    assert result["K1"] == pytest.approx(0.2, rel=1e-2)
