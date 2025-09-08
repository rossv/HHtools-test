import os
from pathlib import Path
import pandas as pd
import pytest
import types
import sys
import subprocess
import hh_tools.extract_timeseries as et
from hh_tools.extract_timeseries import (
    parse_kv_map,
    convert_series_by_dim,
    file_export_dat,
    file_export_csv,
    combine_across_files,
    parse_data_lines,
)

def test_parse_kv_map_basic_and_empty():
    assert parse_kv_map('a=1,b=2') == {'a': '1', 'b': '2'}
    assert parse_kv_map('') == {}
    with pytest.raises(ValueError):
        parse_kv_map('a=1,b')

def test_convert_series_by_dim_flow():
    series = pd.Series([1.0])
    converted = convert_series_by_dim(series, 'flow', 'cfs', 'gpm')
    expected = 1.0 * (1.0 / 0.00222800926)
    assert converted.iloc[0] == pytest.approx(expected)


def test_file_export_dat_no_blank_lines(tmp_path):
    df = pd.DataFrame({
        "M/d/yyyy": pd.to_datetime(["2003-01-01 00:15", "2003-01-01 00:30"]),
        "value": [1.0, 1.1],
    })
    out = tmp_path / "out.dat"
    file_export_dat(
        df.rename(columns={"value": "Total Inflow"}),
        str(out),
        "IDs:\tLBs_1228846\nDate/Time\tTotal Inflow",
        "%m/%d/%Y %H:%M",
        "%.6f",
    )
    lines = out.read_text(encoding="utf-8").splitlines()
    # Ensure there are no blank lines in the output
    assert all(line.strip() for line in lines)
    assert lines[:2] == ["IDs:\tLBs_1228846", "Date/Time\tTotal Inflow"]
    # Expect 2 header lines + 2 data lines
    assert len(lines) == 4


def test_file_export_csv_no_blank_lines(tmp_path):
    df = pd.DataFrame({
        "M/d/yyyy": pd.to_datetime(["2003-01-01 00:15", "2003-01-01 00:30"]),
        "value": [1.0, 1.1],
    })
    out = tmp_path / "out.csv"
    file_export_csv(
        df.rename(columns={"value": "Total Inflow"}),
        str(out),
        "IDs:,LBs_1228846\nDate/Time,Total Inflow",
        "%m/%d/%Y %H:%M",
        "%.6f",
    )
    lines = out.read_text(encoding="utf-8").splitlines()
    assert all(line.strip() for line in lines)
    assert lines[:2] == ["IDs:,LBs_1228846", "Date/Time,Total Inflow"]
    assert len(lines) == 4


def test_module_executes_without_runpy_warning():
    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo_root / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "hh_tools.extract_timeseries", "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=repo_root,
    )
    assert "RuntimeWarning" not in result.stderr


def test_list_ids_option_lists_available_ids(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    stub_root = tmp_path / "stub"
    pkg = stub_root / "swmmtoolbox"
    (pkg / "toolbox_utils" / "src" / "toolbox_utils").mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "def catalog(outfile, item_type):\n"
        "    return [(item_type, 'N1'), (item_type, 'N2')]\n"
    )
    (pkg / "toolbox_utils" / "src" / "toolbox_utils" / "__init__.py").write_text("")
    (pkg / "toolbox_utils" / "src" / "toolbox_utils" / "tsutils.py").write_text("")

    dummy_out = tmp_path / "model.out"
    dummy_out.write_text("dummy")

    env = {
        **os.environ,
        "PYTHONPATH": f"{stub_root}:{repo_root / 'src'}:{repo_root / 'stubs'}",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hh_tools.extract_timeseries",
            str(dummy_out),
            "--list-ids",
            "node",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=repo_root,
    )

    output = result.stdout + result.stderr
    assert "[node] IDs:" in output
    assert "N1" in output and "N2" in output


@pytest.mark.parametrize("fmt", ["dat", "csv"])
def test_plan_elements_respects_combine_for_text_formats(tmp_path, fmt):
    planned = et.plan_elements(
        outfile="/path/model.out",
        item_type="node",
        element_ids=["N1"],
        params=["Flow", "Head"],
        out_format=fmt,
        combine_mode="com",
        outdir_root=str(tmp_path),
        prefix="",
        suffix="",
        dat_template="",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"Flow": "F", "Head": "H"},
    )
    expected = tmp_path / "model" / f"node_N1.{fmt}"
    assert planned == [str(expected)]


@pytest.mark.parametrize("fmt", ["dat", "csv"])
def test_process_elements_combines_params_for_text_formats(tmp_path, monkeypatch, fmt):
    import pandas as pd
    from pathlib import Path

    def fake_extract_series(outfile, item_type, elem_id, param):
        idx = pd.date_range("2020-01-01", periods=2, freq="H")
        base = 1.0 if param == "A" else 3.0
        return pd.DataFrame({"value": [base, base + 1]}, index=idx)

    captured = {}

    def fake_export(df, filename, header, tf, ff):
        captured["df"] = df
        captured["filename"] = filename
        captured["header"] = header
        Path(filename).write_text("ok")

    monkeypatch.setattr(et, "extract_series", fake_extract_series)
    if fmt == "dat":
        monkeypatch.setattr(et, "file_export_dat", fake_export)
    else:
        monkeypatch.setattr(et, "file_export_csv", fake_export)

    files, failures = et.process_elements(
        outfile="dummy.out",
        item_type="node",
        element_ids=["N1"],
        params=["A", "B"],
        out_format=fmt,
        combine_mode="com",
        outdir_root=str(tmp_path),
        time_format="%m/%d/%Y %H:%M",
        float_format="%.6f",
        prefix="",
        suffix="",
        dat_template="",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"A": "A", "B": "B"},
        label_map={"A": "A", "B": "B"},
        param_dimension={},
        assume_units={},
        to_units={},
        unit_overrides={},
        show_progress=False,
    )

    sep = "," if fmt == "csv" else "\t"
    assert len(files) == 1
    assert failures == []
    assert captured["df"].shape[1] == 2
    assert f"Date/Time{sep}A{sep}B" in captured["header"]


def test_sanitize_id_handles_hash():
    # '/' should be replaced but '#' is preserved
    assert et.sanitize_id("N#1/2") == "N#1_2"
    # other unsafe characters are replaced as well
    assert et.sanitize_id("bad*id?") == "bad_id_"


def test_plan_elements_handles_hash_ids(tmp_path):
    planned = et.plan_elements(
        outfile="/path/model.out",
        item_type="node",
        element_ids=["Pump#1"],
        params=["Flow"],
        out_format="dat",
        combine_mode="sep",
        outdir_root=str(tmp_path),
        prefix="",
        suffix="",
        dat_template="",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"Flow": "F"},
    )
    expected = tmp_path / "model" / "F_Pump#1.dat"
    assert planned == [str(expected)]


def test_process_elements_handles_hash_ids(tmp_path, monkeypatch):
    import pandas as pd
    from pathlib import Path

    def fake_extract_series(outfile, item_type, elem_id, param):
        idx = pd.date_range("2020-01-01", periods=1, freq="H")
        return pd.DataFrame({"value": [1.0]}, index=idx)

    captured = {}

    def fake_export(df, filename, header, tf, ff):
        captured["filename"] = filename
        Path(filename).write_text("ok")

    monkeypatch.setattr(et, "extract_series", fake_extract_series)
    monkeypatch.setattr(et, "file_export_dat", fake_export)

    files, failures = et.process_elements(
        outfile="dummy.out",
        item_type="node",
        element_ids=["Pump#1"],
        params=["Flow"],
        out_format="dat",
        combine_mode="sep",
        outdir_root=str(tmp_path),
        time_format="%m/%d/%Y %H:%M",
        float_format="%.6f",
        prefix="",
        suffix="",
        dat_template="",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"Flow": "F"},
        label_map={"Flow": "Flow"},
        param_dimension={},
        assume_units={},
        to_units={},
        unit_overrides={},
        show_progress=False,
    )

    assert failures == []
    assert files == [str(tmp_path / "dummy" / "F_Pump#1.dat")]
    assert captured["filename"].endswith("F_Pump#1.dat")


def test_plan_elements_handles_period_ids(tmp_path):
    planned = et.plan_elements(
        outfile="/path/model.out",
        item_type="node",
        element_ids=["Pump.1"],
        params=["Flow"],
        out_format="dat",
        combine_mode="sep",
        outdir_root=str(tmp_path),
        prefix="",
        suffix="",
        dat_template="",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"Flow": "F"},
    )
    expected = tmp_path / "model" / "F_Pump.1.dat"
    assert planned == [str(expected)]


def test_process_elements_handles_period_ids(tmp_path, monkeypatch):
    import pandas as pd
    from pathlib import Path

    def fake_extract_series(outfile, item_type, elem_id, param):
        idx = pd.date_range("2020-01-01", periods=1, freq="H")
        return pd.DataFrame({"value": [1.0]}, index=idx)

    captured = {}

    def fake_export(df, filename, header, tf, ff):
        captured["filename"] = filename
        Path(filename).write_text("ok")

    monkeypatch.setattr(et, "extract_series", fake_extract_series)
    monkeypatch.setattr(et, "file_export_dat", fake_export)

    files, failures = et.process_elements(
        outfile="dummy.out",
        item_type="node",
        element_ids=["Pump.1"],
        params=["Flow"],
        out_format="dat",
        combine_mode="sep",
        outdir_root=str(tmp_path),
        time_format="%m/%d/%Y %H:%M",
        float_format="%.6f",
        prefix="",
        suffix="",
        dat_template="",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"Flow": "F"},
        label_map={"Flow": "Flow"},
        param_dimension={},
        assume_units={},
        to_units={},
        unit_overrides={},
        show_progress=False,
    )

    assert failures == []
    assert files == [str(tmp_path / "dummy" / "F_Pump.1.dat")]
    assert captured["filename"].endswith("F_Pump.1.dat")


def test_main_respects_output_dir(tmp_path, monkeypatch):
    dummy_out = tmp_path / "model.out"
    dummy_out.write_text("dummy")

    captured = {}

    def fake_process_elements(*, outdir_root, **kwargs):
        captured["outdir_root"] = outdir_root
        return [], []

    dummy_swmm = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "swmmtoolbox", types.SimpleNamespace(swmmtoolbox=dummy_swmm))
    monkeypatch.setitem(sys.modules, "swmmtoolbox.swmmtoolbox", dummy_swmm)

    monkeypatch.setattr(et, "process_elements", fake_process_elements)
    monkeypatch.setattr(et, "discover_ids", lambda *args, **kwargs: ["N1"])

    et.main([
        str(dummy_out),
        "--types", "node",
        "--node-params", "Flow_rate",
        "--output-dir", str(tmp_path / "out"),
    ])

    assert captured["outdir_root"] == str(tmp_path / "out")


def test_default_param_dim_includes_pump_status():
    assert et.DEFAULT_PARAM_DIM.get("Pump_status") == "other"


def test_main_creates_pptx(tmp_path, monkeypatch):
    dummy_out = tmp_path / "model.out"
    dummy_out.write_text("dummy")

    captured = {}

    def fake_process_elements(*, ppt=None, **kwargs):
        captured["ppt"] = ppt
        return [], []

    class DummyPresentation:
        def __init__(self):
            self.saved = False

        def save(self, path):
            captured["save_path"] = path

    dummy_swmm = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "swmmtoolbox", types.SimpleNamespace(swmmtoolbox=dummy_swmm))
    monkeypatch.setitem(sys.modules, "swmmtoolbox.swmmtoolbox", dummy_swmm)

    monkeypatch.setattr(et, "process_elements", fake_process_elements)
    monkeypatch.setattr(et, "discover_ids", lambda *args, **kwargs: ["N1"])
    monkeypatch.setitem(sys.modules, "pptx", types.SimpleNamespace(Presentation=DummyPresentation))

    pptx_path = tmp_path / "out.pptx"
    et.main([
        str(dummy_out),
        "--types", "node",
        "--node-params", "Flow_rate",
        "--pptx", str(pptx_path),
    ])

    assert isinstance(captured["ppt"], DummyPresentation)
    assert captured["save_path"] == str(pptx_path)


def test_combine_across_files_stacks_chronologically(tmp_path):
    df1 = pd.DataFrame({
        "M/d/yyyy": pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00"]),
        "value": [1.0, 2.0],
    })
    df2 = pd.DataFrame({
        "M/d/yyyy": pd.to_datetime(["2020-01-01 02:00", "2020-01-01 03:00"]),
        "value": [3.0, 4.0],
    })
    f1 = tmp_path / "part1.dat"
    f2 = tmp_path / "part2.dat"
    file_export_dat(df1.rename(columns={"value": "Flow"}), str(f1), "IDs:\tN1\nDate/Time\tFlow", "%m/%d/%Y %H:%M", "%.6f")
    file_export_dat(df2.rename(columns={"value": "Flow"}), str(f2), "IDs:\tN1\nDate/Time\tFlow", "%m/%d/%Y %H:%M", "%.6f")

    combine_across_files([( "node", str(f1)), ( "node", str(f2))], "dat", str(tmp_path))

    out = tmp_path / "combined" / "Flow_N1.dat"
    rows = parse_data_lines(str(out), skip=1)
    times = [ts for ts, _ in rows]
    assert times == sorted(times)
    assert len(times) == 4


def test_combine_across_files_csv(tmp_path):
    df1 = pd.DataFrame({
        "M/d/yyyy": pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00"]),
        "value": [1.0, 2.0],
    })
    df2 = pd.DataFrame({
        "M/d/yyyy": pd.to_datetime(["2020-01-01 02:00", "2020-01-01 03:00"]),
        "value": [3.0, 4.0],
    })
    f1 = tmp_path / "part1.csv"
    f2 = tmp_path / "part2.csv"
    file_export_csv(df1.rename(columns={"value": "Flow"}), str(f1), "IDs:,N1\nDate/Time,Flow", "%m/%d/%Y %H:%M", "%.6f")
    file_export_csv(df2.rename(columns={"value": "Flow"}), str(f2), "IDs:,N1\nDate/Time,Flow", "%m/%d/%Y %H:%M", "%.6f")

    combine_across_files([( "node", str(f1)), ( "node", str(f2))], "csv", str(tmp_path))

    out = tmp_path / "combined" / "Flow_N1.csv"
    rows = parse_data_lines(str(out), skip=1)
    times = [ts for ts, _ in rows]
    assert times == sorted(times)
    assert len(times) == 4


def test_process_elements_continues_on_extract_error(tmp_path, monkeypatch, caplog):
    import pandas as pd

    def fake_extract_series(outfile, item_type, elem_id, param):
        if elem_id == "bad":
            raise ValueError("No objects to concatenate")
        idx = pd.date_range("2020-01-01", periods=2, freq="H")
        return pd.DataFrame({"value": [1.0, 2.0]}, index=idx)

    monkeypatch.setattr(et, "extract_series", fake_extract_series)
    monkeypatch.setattr(
        et,
        "file_export_dat",
        lambda df, filename, header, tf, ff: Path(filename).write_text("ok"),
    )

    files, failures = et.process_elements(
        outfile="dummy.out",
        item_type="node",
        element_ids=["good", "bad"],
        params=["Flow_rate"],
        out_format="dat",
        combine_mode="sep",
        outdir_root=str(tmp_path),
        time_format="%m/%d/%Y %H:%M",
        float_format="%.6f",
        prefix="",
        suffix="",
        dat_template="{prefix}{type}_{id}_{param}{suffix}",
        tsf_template_sep="",
        tsf_template_com="",
        param_short={"Flow_rate": "Flow"},
        label_map={"Flow_rate": "Flow"},
        param_dimension={},
        assume_units={},
        to_units={},
        unit_overrides={},
        show_progress=False,
    )

    assert len(files) == 1
    assert len(failures) == 1
    assert failures[0][2] == "bad"
    assert "bad" in caplog.text
