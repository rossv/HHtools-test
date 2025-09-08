import pandas as pd
import pytest

from hh_tools import summarize_outfiles


def _make_df(values):
    t = pd.date_range("2020-01-01", periods=len(values), freq="H")
    return pd.DataFrame({"Datetime": t, "value": values})


def test_single_file_summary(monkeypatch):
    def fake_extract(outfile, item_type, element_id, param):
        return _make_df([0.0, 2.0, 1.0])

    monkeypatch.setattr(summarize_outfiles, "extract_series", fake_extract)
    records = summarize_outfiles.summarize(["a.out"], "node", ["J1"], ["Flow"])
    assert len(records) == 1
    rec = records[0]
    assert rec["file"] == "a.out"
    assert rec["id"] == "J1"
    assert rec["param"] == "Flow"
    assert rec["peak"] == 2.0
    assert rec["mean"] == pytest.approx(1.0)
    assert rec["total_volume"] == pytest.approx(10800.0)
    assert rec["time_to_peak"] == 3600.0


def test_multiple_files_summary(monkeypatch):
    def fake_extract(outfile, item_type, element_id, param):
        if outfile == "a.out":
            return _make_df([0.0, 2.0, 1.0])
        else:
            return _make_df([1.0, 3.0, 2.0])

    monkeypatch.setattr(summarize_outfiles, "extract_series", fake_extract)
    files = ["a.out", "b.out"]
    records = summarize_outfiles.summarize(files, "node", ["J1"], ["Flow"])
    assert len(records) == 2
    rec_a = next(r for r in records if r["file"] == "a.out")
    rec_b = next(r for r in records if r["file"] == "b.out")
    assert rec_a["peak"] == 2.0
    assert rec_b["peak"] == 3.0
