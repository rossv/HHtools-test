from pathlib import Path

import logging
import pandas as pd
import hh_tools.compare_outfiles as co


def test_compare_series_basic():
    t = pd.date_range("2020-01-01", periods=2, freq="H")
    a = pd.DataFrame({"Datetime": t, "value": [1.0, 3.0]})
    b = pd.DataFrame({"Datetime": t, "value": [1.0, 4.0]})
    max_diff, mean_diff = co.compare_series(a, b)
    assert max_diff == 1.0
    assert mean_diff == 0.5


def test_compare_series_no_overlap():
    t1 = pd.date_range("2020-01-01", periods=2, freq="H")
    t2 = pd.date_range("2020-01-03", periods=2, freq="H")
    a = pd.DataFrame({"Datetime": t1, "value": [1.0, 3.0]})
    b = pd.DataFrame({"Datetime": t2, "value": [1.0, 4.0]})
    max_diff, mean_diff = co.compare_series(a, b)
    assert pd.isna(max_diff)
    assert pd.isna(mean_diff)


def test_build_diff_table(monkeypatch):
    t = pd.date_range("2020-01-01", periods=2, freq="H")

    def fake_extract(outfile, item_type, element_id, param):
        if outfile == "f1":
            return pd.DataFrame({"Datetime": t, "value": [1.0, 3.0]})
        return pd.DataFrame({"Datetime": t, "value": [1.0, 4.0]})

    monkeypatch.setattr(co, "extract_series", fake_extract)
    df = co.build_diff_table("f1", "f2", "node", "N1", "Flow_rate")
    assert list(df.columns) == ["Datetime", "value_1", "value_2", "diff"]
    assert df["diff"].tolist() == [0.0, -1.0]


def test_extract_series_logs_and_falls_back(monkeypatch, caplog):
    calls = []

    def fake_extract(outfile, args):
        calls.append(args)
        if isinstance(args, list):
            raise TypeError("list format not supported")
        return pd.Series([1.0], index=pd.date_range("2020-01-01", periods=1))

    import types
    import sys

    fake_pkg = types.ModuleType("swmmtoolbox")
    fake_module = types.SimpleNamespace(extract=fake_extract)
    fake_pkg.swmmtoolbox = fake_module
    monkeypatch.setitem(sys.modules, "swmmtoolbox", fake_pkg)
    monkeypatch.setitem(sys.modules, "swmmtoolbox.swmmtoolbox", fake_module)

    with caplog.at_level(logging.ERROR):
        df = co.extract_series("f.out", "node", "N1", "Flow_rate")

    assert not df.empty
    assert calls == [["node", "N1", "Flow_rate"], "node,N1,Flow_rate"]
    assert any("retrying" in rec.message for rec in caplog.records)


def test_cli_writes_detailed_table(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=1, freq="H")
    fake_df = pd.DataFrame({
        "Datetime": t,
        "value_1": [1.0],
        "value_2": [2.0],
        "diff": [-1.0],
    })
    monkeypatch.setattr(co, "discover_ids", lambda f, t: ["N1"])
    monkeypatch.setattr(co, "build_diff_table", lambda *args: fake_df)
    out_path = tmp_path / "report.csv"
    detailed = tmp_path / "detailed.csv"
    rc = co.main([
        "f1.out",
        "f2.out",
        "--ids",
        "N1",
        "--params",
        "Flow_rate",
        "--output",
        str(out_path),
        "--detailed-table",
        str(detailed),
        "--quiet",
    ])
    assert rc == 0
    assert out_path.exists()
    assert detailed.exists()


def test_cli_plot_dir(tmp_path, monkeypatch):
    t = pd.date_range("2020-01-01", periods=1, freq="H")
    fake_df = pd.DataFrame({
        "Datetime": t,
        "value_1": [1.0],
        "value_2": [2.0],
        "diff": [-1.0],
    })
    monkeypatch.setattr(co, "discover_ids", lambda f, t: ["N1"])
    monkeypatch.setattr(co, "build_diff_table", lambda *args: fake_df)

    def fake_plot(df, param, path: Path) -> None:
        Path(path).write_text("plot")

    monkeypatch.setattr(co, "plot_series", fake_plot)

    out_path = tmp_path / "report.csv"
    plot_dir = tmp_path / "plots"
    rc = co.main([
        "f1.out",
        "f2.out",
        "--ids",
        "N1",
        "--params",
        "Flow_rate",
        "--output",
        str(out_path),
        "--plot-dir",
        str(plot_dir),
        "--quiet",
    ])
    assert rc == 0
    expected = plot_dir / "N1_Flow_rate.png"
    assert expected.exists()
