import pandas as pd

from hh_tools import event_extractor as ee


def test_event_extraction_and_export(tmp_path):
    times = pd.date_range("2020-01-01", periods=10, freq="10min")
    values = [0, 0.2, 0.3, 0, 0, 0.1, 0.2, 0.3, 0, 0]
    df = pd.DataFrame({"time": times, "rain": values})
    csv_path = tmp_path / "rain.csv"
    df.to_csv(csv_path, index=False)
    outdir = tmp_path / "events"
    ee.main([
        str(csv_path),
        "--threshold",
        "0.15",
        "--min-duration",
        "20",
        "--output-dir",
        str(outdir),
    ])
    files = sorted(outdir.glob("*.csv"))
    assert len(files) == 2
    first = pd.read_csv(files[0])
    assert first.shape[0] == 2
