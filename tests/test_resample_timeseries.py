import pytest
import pandas as pd

from hh_tools import resample_timeseries as rt


def test_resample_and_export_csv(tmp_path):
    times = pd.date_range("2020-01-01", periods=6, freq="10min")
    values = [0, 1, 2, 3, 4, 5]
    df = pd.DataFrame({"time": times, "val": values})
    csv = tmp_path / "series.csv"
    df.to_csv(csv, index=False)
    out = tmp_path / "res.csv"
    rt.main([str(csv), "--freq", "20min", "--output", str(out), "--format", "csv"])
    out_df = pd.read_csv(out)
    assert out_df.shape[0] == 3
    assert out_df.iloc[1, 1] == pytest.approx(2.5)
