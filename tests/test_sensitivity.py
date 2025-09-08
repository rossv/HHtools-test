import json
from pathlib import Path

import pandas as pd
import pytest

from hh_tools import sensitivity


def fake_runner(inp_path: Path, metrics, swmm_exe: str = "swmm5"):
    text = inp_path.read_text()
    params = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            params[k.strip()] = float(v.strip())
    res = {}
    if "peak_flow" in metrics:
        res["peak_flow"] = params.get("a", 0.0) * params.get("b", 0.0)
    if "runoff_volume" in metrics:
        res["runoff_volume"] = params.get("a", 0.0) + params.get("b", 0.0)
    return res


def test_sensitivity_analysis(tmp_path):
    base_inp = tmp_path / "base.inp"
    base_inp.write_text("a=$a\nb=$b\n")
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps({"a": [1, 2], "b": [5]}))

    ranges = sensitivity.load_param_ranges(params_file)
    df = sensitivity.sensitivity_analysis(base_inp, ranges, ["peak_flow"], runner=fake_runner)
    assert df.shape[0] == 2
    assert list(df["a"]) == [1, 2]
    assert list(df["peak_flow"]) == [5, 10]


def test_cli_sensitivity(tmp_path, monkeypatch):
    base_inp = tmp_path / "base.inp"
    base_inp.write_text("a=$a\nb=$b\n")
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps({"a": [1], "b": [2]}))
    out_csv = tmp_path / "out.csv"

    monkeypatch.setattr(sensitivity, "run_swmm", fake_runner)

    sensitivity.main([
        str(base_inp),
        "--params",
        str(params_file),
        "--metrics",
        "peak_flow,runoff_volume",
        "--output",
        str(out_csv),
    ])

    df = pd.read_csv(out_csv)
    assert list(df.columns) == ["a", "b", "peak_flow", "runoff_volume"]
    assert df["peak_flow"].iloc[0] == 2
    assert df["runoff_volume"].iloc[0] == 3
