import pandas as pd
from hh_tools.review_flow_data import detect_spikes, main


def test_exported_timestamps_match_source(tmp_path):
    src = pd.DataFrame(
        {
            "Time": pd.date_range("2020-01-01", periods=3, freq="H"),
            "Flow": [1.0, 2.0, 3.0],
        }
    )
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.tsf"
    src.to_csv(inp, index=False)

    main([str(inp), "--time-col", "Time", "--flow-col", "Flow", "--output", str(out)])

    df_out = pd.read_csv(out, sep="\t", skiprows=2, parse_dates=[0], names=["Datetime", "Flow"])
    assert list(df_out["Datetime"]) == list(src["Time"])

def test_detect_spikes_identifies_single_point():
    idx = pd.date_range('2020-01-01', periods=5, freq='H')
    s = pd.Series([1.0, 1.0, 10.0, 1.0, 1.0], index=idx)
    spikes = detect_spikes(s, threshold=0.3)
    assert list(spikes) == [idx[2]]
