import io
from datetime import datetime

import pandas as pd
import pytest

import hh_tools.download_rainfall as dr


class DummyResponse:
    def __init__(self, text="", json_data=None, headers=None, status=200):
        self.text = text
        self._json = json_data
        self.headers = headers or {}
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")


def test_fetch_rainfall_json(monkeypatch):
    sample = {"data": [
        {"date": "2023-01-01T00:00", "value": 1.0},
        {"date": "2023-01-01T01:00", "value": 2.0},
    ]}

    def fake_get(url, params, timeout):
        assert params["station"] == "ABC"
        return DummyResponse(json_data=sample, headers={"Content-Type": "application/json"})

    monkeypatch.setattr(dr.requests, "get", fake_get)
    df = dr.fetch_rainfall("ABC", "2023-01-01", "2023-01-02", "k")
    assert list(df["Rainfall"]) == [1.0, 2.0]
    assert df["Datetime"].iloc[0] == pd.Timestamp("2023-01-01T00:00")


def test_fetch_rainfall_csv(monkeypatch):
    csv_text = "date,value\n2023-01-01T00:00,1.0\n2023-01-01T01:00,2.0\n"

    def fake_get(url, params, timeout):
        return DummyResponse(text=csv_text, headers={"Content-Type": "text/csv"})

    monkeypatch.setattr(dr.requests, "get", fake_get)
    df = dr.fetch_rainfall("ABC", "2023-01-01", "2023-01-02", "k")
    assert df.shape == (2, 2)
    assert df["Rainfall"].sum() == pytest.approx(3.0)


def test_main_writes_tsf(tmp_path, monkeypatch):
    df = pd.DataFrame({
        "Datetime": [pd.Timestamp("2023-01-01 00:00"), pd.Timestamp("2023-01-01 01:00")],
        "Rainfall": [1.0, 2.0],
    })
    monkeypatch.setattr(dr, "fetch_rainfall", lambda *a, **k: df)
    out = tmp_path / "rain.tsf"
    args = [
        "--station", "ABC",
        "--start", "2023-01-01",
        "--end", "2023-01-02",
        "--api-key", "k",
        "--output", str(out),
        "--format", "tsf",
        "--units", "mm",
    ]
    dr.main(args)
    text = out.read_text().splitlines()
    assert text[0] == "IDs:\tABC"
    assert text[2].startswith("Datetime\tRainfall")


def test_fetch_rainfall_noaa(monkeypatch):
    # Ensure NOAA-specific parameters and headers are used and that a helpful
    # error is raised when no data are returned.
    called = {}

    def fake_get(url, params, headers, timeout):
        called["params"] = params
        called["headers"] = headers
        # Empty JSON payload to trigger the "no data" error
        return DummyResponse(json_data={"results": []}, headers={"Content-Type": "application/json"})

    monkeypatch.setattr(dr.requests, "get", fake_get)
    with pytest.raises(ValueError):
        dr.fetch_rainfall(
            "US1",
            "2023-01-01",
            "2023-01-02",
            "token",
            url=dr.NOAA_URL,
            dataset="GHCND",
            datatype="PRCP",
        )
    assert called["headers"]["token"] == "token"
    assert called["params"]["datasetid"] == "GHCND"
    assert called["params"]["datatypeid"] == "PRCP"
    assert called["params"]["stationid"] == "GHCND:US1"


@pytest.mark.parametrize(
    "dataset,datatype",
    [(None, "PRCP"), ("GHCND", None)],
)
def test_fetch_rainfall_requires_dataset_datatype(dataset, datatype, monkeypatch):
    def fake_get(*args, **kwargs):
        raise AssertionError("requests.get should not be called")

    monkeypatch.setattr(dr.requests, "get", fake_get)
    with pytest.raises(ValueError, match="dataset and datatype"):
        dr.fetch_rainfall(
            "US1",
            "2023-01-01",
            "2023-01-02",
            "token",
            url=dr.NOAA_URL,
            dataset=dataset,
            datatype=datatype,
        )


def test_fetch_rainfall_prefixed_station(monkeypatch):
    called = {}

    def fake_get(url, params, headers, timeout):
        called["params"] = params
        called["headers"] = headers
        sample = {"results": [{"date": "2023-01-01T00:00", "value": 1.0}]}
        return DummyResponse(json_data=sample, headers={"Content-Type": "application/json"})

    monkeypatch.setattr(dr.requests, "get", fake_get)
    df = dr.fetch_rainfall(
        "GHCND:US1",
        "2023-01-01",
        "2023-01-02",
        "token",
        url=dr.NOAA_URL,
        dataset="GHCND",
        datatype="PRCP",
    )
    assert called["params"]["stationid"] == "GHCND:US1"
    assert df["Rainfall"].iloc[0] == 1.0


def test_search_stations_uses_query(monkeypatch):
    called = {}

    def fake_get(url, headers, params, timeout):
        called["params"] = params
        return DummyResponse(
            json_data={
                "results": [
                    {"id": "1", "name": "Foo Station"},
                    {"id": "2", "name": "Bar"},
                ]
            },
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    df = dr.search_stations("token", "foo")
    assert called["params"]["q"] == "foo"
    assert list(df["name"]) == ["Foo Station"]


def test_search_stations_handles_regex(monkeypatch):
    """Queries with regex characters are treated literally."""

    def fake_get(url, headers, params, timeout):
        return DummyResponse(
            json_data={
                "results": [
                    {"id": "A1", "name": "Station*One"},
                    {"id": "B*2", "name": "Another"},
                    {"id": "C3", "name": "Plain"},
                ]
            },
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    df = dr.search_stations("token", "*")
    assert list(df["id"]) == ["A1", "B*2"]


def test_search_stations_missing_columns(monkeypatch):
    """Returns empty DataFrame when required keys are missing."""

    def fake_get(url, headers, params, timeout):
        return DummyResponse(
            json_data={"results": [{"foo": 1}, {"bar": 2}]},
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    df = dr.search_stations("token", "anything")
    assert df.empty
    assert list(df.columns) == ["id", "name"]


def test_available_datasets(monkeypatch):
    called = {}

    def fake_get(url, headers, params, timeout):
        called["url"] = url
        called["params"] = params
        called["headers"] = headers
        return DummyResponse(
            json_data={
                "results": [
                    {
                        "id": "GHCND",
                        "name": "Daily Summaries",
                        "mindate": "2000-01-01",
                        "maxdate": "2020-01-01",
                    },
                    {
                        "id": "PRECIP_15",
                        "name": "15 Minute Precip",
                        "mindate": "2010-01-01",
                        "maxdate": "2020-01-01",
                    },
                ]
            },
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    datasets = dr.available_datasets("GHCND:US1", "token")
    assert called["url"].endswith("/datasets")
    assert called["params"]["stationid"] == "GHCND:US1"
    assert datasets == [
        {
            "id": "GHCND",
            "name": "Daily Summaries",
            "mindate": "2000-01-01",
            "maxdate": "2020-01-01",
        },
        {
            "id": "PRECIP_15",
            "name": "15 Minute Precip",
            "mindate": "2010-01-01",
            "maxdate": "2020-01-01",
        },
    ]


def test_available_datatypes(monkeypatch):
    called = {}

    def fake_get(url, headers, params, timeout):
        called["url"] = url
        called["params"] = params
        called["headers"] = headers
        return DummyResponse(
            json_data={
                "results": [
                    {"id": "PRCP", "name": "Precipitation"},
                    {"id": "SNOW", "name": "Snow"},
                ]
            },
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    datatypes = dr.available_datatypes("GHCND:US1", "GHCND", "token")
    assert called["url"].endswith("/datatypes")
    assert called["params"]["datasetid"] == "GHCND"
    assert called["params"]["stationid"] == "GHCND:US1"
    assert datatypes == [
        ("PRCP", "Precipitation"),
        ("SNOW", "Snow"),
    ]


def test_find_stations_by_city_limit(monkeypatch):
    called = {}

    def fake_get(url, headers=None, params=None, timeout=30):
        if "nominatim" in url:
            return DummyResponse(
                json_data=[{"lat": "1", "lon": "2"}],
                headers={"Content-Type": "application/json"},
            )
        called["params"] = params
        return DummyResponse(
            json_data={"results": []},
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    res = dr.find_stations_by_city("Somewhere", {"token": "t"})
    assert called["params"]["limit"] == 100
    assert res == []


def test_find_stations_by_city_geocode_extent(monkeypatch):
    """Geocoding is performed and the buffer defines the search extent."""
    calls = {}

    def fake_get(url, headers=None, params=None, timeout=30):
        if "nominatim" in url:
            calls["geo"] = (headers, params)
            return DummyResponse(
                json_data=[{"lat": "10", "lon": "20"}],
                headers={"Content-Type": "application/json"},
            )
        calls["extent"] = params["extent"]
        return DummyResponse(
            json_data={"results": []},
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    dr.find_stations_by_city("Testville", {"token": "t"}, buffer=0.5)

    geo_headers, geo_params = calls["geo"]
    assert geo_params["q"] == "Testville"
    assert "User-Agent" in geo_headers
    assert calls["extent"] == f"{10-0.5},{20-0.5},{10+0.5},{20+0.5}"


def test_find_stations_by_city_metadata(monkeypatch):
    """Returned station dictionaries include metadata fields."""

    def fake_get(url, headers=None, params=None, timeout=30):
        if "nominatim" in url:
            return DummyResponse(
                json_data=[{"lat": "1", "lon": "2"}],
                headers={"Content-Type": "application/json"},
            )
        return DummyResponse(
            json_data={
                "results": [
                    {
                        "id": "ST1",
                        "name": "Station 1",
                        "latitude": 1.0,
                        "longitude": 2.0,
                        "mindate": "2000-01-01",
                        "maxdate": "2023-12-31",
                        "datacoverage": 0.5,
                    }
                ]
            },
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(dr.requests, "get", fake_get)
    res = dr.find_stations_by_city("Somewhere", {"token": "t"})
    assert res == [
        {
            "id": "ST1",
            "name": "Station 1",
            "latitude": 1.0,
            "longitude": 2.0,
            "mindate": "2000-01-01",
            "maxdate": "2023-12-31",
            "datacoverage": 0.5,
        }
    ]
