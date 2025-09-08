import pandas as pd
import pytest

import hh_tools.download_streamflow as ds


class DummyResponse:
    def __init__(self, json_data=None, status=200):
        self._json = json_data
        self.headers = {"Content-Type": "application/json"}
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")


def _sample_payload():
    return {
        "value": {
            "timeSeries": [
                {
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "1.0",
                                    "dateTime": "2023-01-01T00:00:00.000-06:00",
                                },
                                {
                                    "value": "2.0",
                                    "dateTime": "2023-01-01T01:00:00.000-06:00",
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }


def test_fetch_streamflow(monkeypatch):
    def fake_get(url, params, timeout):
        assert params["sites"] == "123"
        assert params["parameterCd"] == "00060"
        return DummyResponse(json_data=_sample_payload())

    monkeypatch.setattr(ds.requests, "get", fake_get)
    df = ds.fetch_streamflow("123", "2023-01-01", "2023-01-02")
    assert list(df["Flow"]) == [1.0, 2.0]
    assert df["Datetime"].iloc[0] == pd.Timestamp("2023-01-01 00:00")


def test_fetch_streamflow_units(monkeypatch):
    def fake_get(url, params, timeout):
        return DummyResponse(json_data=_sample_payload())

    monkeypatch.setattr(ds.requests, "get", fake_get)
    df = ds.fetch_streamflow("123", "2023-01-01", "2023-01-02", units="m3/s")
    assert df["Flow"].iloc[0] == pytest.approx(0.0283168)


def test_aggregate_streamflow():
    df = pd.DataFrame(
        {
            "Datetime": pd.date_range("2023-01-01", periods=4, freq="15min"),
            "Flow": [1.0, 2.0, 3.0, 4.0],
        }
    )
    agg = ds.aggregate_streamflow(df, "H")
    assert agg.shape[0] == 1
    assert agg["Flow"].iloc[0] == pytest.approx(2.5)


def test_main_writes_files(tmp_path, monkeypatch):
    df = pd.DataFrame(
        {
            "Datetime": [pd.Timestamp("2023-01-01 00:00"), pd.Timestamp("2023-01-01 01:00")],
            "Flow": [1.0, 2.0],
        }
    )
    monkeypatch.setattr(ds, "fetch_streamflow", lambda *a, **k: df)
    base = tmp_path / "out"
    args = [
        "--station",
        "123",
        "--start",
        "2023-01-01",
        "--end",
        "2023-01-02",
        "--output",
        str(base),
        "--format",
        "csv",
    ]
    ds.main(args)
    csv_file = base.with_suffix(".csv")
    assert csv_file.exists()

    args[-1] = "tsf"
    ds.main(args)
    tsf_file = base.with_suffix(".tsf")
    assert tsf_file.exists()
    lines = tsf_file.read_text().splitlines()
    assert lines[0] == "IDs:\t123"
    assert lines[2] == "Date/Time\tFlow"
    assert lines[3] == "01/01/2023 00:00\t1.0"

    args[-1] = "swmm"
    ds.main(args)
    swmm_file = base.with_suffix(".swmm")
    assert swmm_file.exists()
    text = swmm_file.read_text().splitlines()
    assert text[0] == "[TIMESERIES]"


def test_search_stations(monkeypatch):
    def fake_get(url, params, timeout):
        assert params["siteName"] == "foo"
        return DummyResponse(
            json_data={
                "value": {
                    "sites": [
                        {"siteCode": [{"value": "1"}], "siteName": "Foo River"},
                        {"siteCode": [{"value": "2"}], "siteName": "Bar"},
                    ]
                }
            }
        )

    monkeypatch.setattr(ds.requests, "get", fake_get)
    df = ds.search_stations("foo")
    assert list(df["id"]) == ["1"]


def test_search_stations_missing_columns(monkeypatch):
    def fake_get(url, params, timeout):
        return DummyResponse(json_data={"value": {"sites": [{"foo": 1}]}})

    monkeypatch.setattr(ds.requests, "get", fake_get)
    df = ds.search_stations("foo")
    assert df.empty
    assert list(df.columns) == ["id", "name"]


def test_find_stations_by_city_skips_missing(monkeypatch):
    """Entries lacking an id or name are excluded from results."""

    def fake_get(url, params=None, headers=None, timeout=30):
        if "nominatim" in url:
            return DummyResponse(json_data=[{"lat": "1", "lon": "2"}])
        return DummyResponse(
            json_data={
                "value": {
                    "sites": [
                        {
                            "siteCode": [{"value": "1"}],
                            "siteName": "Station 1",
                            "geoLocation": {"geogLocation": {"latitude": 1.0, "longitude": 2.0}},
                        },
                        {  # Missing id
                            "siteCode": [{}],
                            "siteName": "No ID",
                            "geoLocation": {"geogLocation": {"latitude": 3.0, "longitude": 4.0}},
                        },
                        {  # Missing name
                            "siteCode": [{"value": "3"}],
                            "siteName": "",
                            "geoLocation": {"geogLocation": {"latitude": 5.0, "longitude": 6.0}},
                        },
                    ]
                }
            }
        )

    monkeypatch.setattr(ds.requests, "get", fake_get)
    res = ds.find_stations_by_city("Somewhere")
    assert res == [
        {"id": "1", "name": "Station 1", "latitude": 1.0, "longitude": 2.0}
    ]
