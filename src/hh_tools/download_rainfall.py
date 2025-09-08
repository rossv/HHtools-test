#!/usr/bin/env python3
"""Utilities for downloading rainfall data.

This module provides a small wrapper around the NOAA CDO web API and a generic
fallback service used in the tests.  The public functions are intentionally
simple so that they can be unit tested without relying on the network.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd
import requests
import logging

# Base URLs used by the helpers below
NOAA_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"
STATION_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/stations"


def fetch_rainfall(
    station: str,
    start: str,
    end: str,
    api_key: str,
    *,
    url: str = "https://example.com/rainfall",
    dataset: str | None = None,
    datatype: str | None = None,
    units: str = "mm",
    timeout: int = 30,
) -> pd.DataFrame:
    """Fetch rainfall for ``station`` between ``start`` and ``end``.

    The behaviour changes slightly depending on ``url``.  When ``url`` is
    :data:`NOAA_URL` the request follows the requirements of the NOAA CDO API
    (token header, dataset and datatype identifiers, etc.).  For any other URL a
    small dummy service is assumed which simply echoes back ``station``,
    ``start`` and ``end``.  The tests monkeypatch :func:`requests.get` so no
    external HTTP requests are made.
    """

    if url == NOAA_URL:
        if dataset is None or datatype is None:
            raise ValueError(
                "dataset and datatype must be provided for NOAA requests"
            )
        stationid = station if ":" in station else f"{dataset}:{station}"
        params = {
            "datasetid": dataset,
            "stationid": stationid,
            "datatypeid": datatype,
            "startdate": start,
            "enddate": end,
            "units": "metric" if units == "mm" else "standard",
            "limit": 1000,
        }
        headers = {"token": api_key}
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    else:
        params = {
            "station": station,
            "start": start,
            "end": end,
            "token": api_key,
        }
        response = requests.get(url, params=params, timeout=timeout)

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        payload = response.json()
        records = payload.get("results") or payload.get("data") or []
        if not records:
            raise ValueError("No rainfall data returned")
        df = pd.DataFrame.from_records(records)
    elif "text/csv" in content_type:
        df = pd.read_csv(io.StringIO(response.text))
    else:
        raise ValueError("Unsupported response format")

    # Normalise column names
    if "date" in df.columns:
        df["Datetime"] = pd.to_datetime(df["date"])
    elif "Datetime" not in df.columns:
        raise ValueError("Response missing 'date' field")

    if "value" in df.columns:
        df["Rainfall"] = df["value"]
    elif "Rainfall" not in df.columns:
        raise ValueError("Response missing 'value' field")

    return df[["Datetime", "Rainfall"]]


def search_stations(token: str, query: str, *, timeout: int = 30) -> pd.DataFrame:
    """Search for stations whose name contains ``query``.

    Returns a :class:`pandas.DataFrame` with columns ``id`` and ``name``.  The
    function only performs a basic case-insensitive filter of the returned
    results so that it behaves deterministically for the unit tests.
    """

    params = {
        "datasetid": "GHCND",
        "datatypeid": "PRCP",
        "limit": 1000,
        "q": query,
    }
    headers = {"token": token}
    r = requests.get(STATION_URL, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("results", [])
    df = pd.DataFrame(data)

    # Ensure required columns are present
    if df.empty or not {"id", "name"}.issubset(df.columns):
        return pd.DataFrame(columns=["id", "name"])

    df = df[["id", "name"]]
    mask = (
        df["name"].str.contains(query, case=False, na=False, regex=False)
        | df["id"].str.contains(query, case=False, na=False, regex=False)
    )
    return df[mask].reset_index(drop=True)


def find_stations_by_city(
    city: str,
    headers: dict,
    *,
    buffer: float = 0.25,
    timeout: int = 30,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Locate stations near ``city`` using a simple bounding box search.

    The function first geocodes the city name via OpenStreetMap's Nominatim
    service and then queries the NOAA station endpoint for stations within a
    latitude/longitude extent.  ``limit`` controls the maximum number of
    stations returned which keeps the GUI responsive when plotting results on a
    map.  A list of dictionaries is returned where each entry contains the
    station ``id``, ``name``, ``latitude`` and ``longitude`` as well as the
    station's ``mindate``/``maxdate`` range and ``datacoverage`` value.  The
    ``headers`` argument mirrors the historic interface used by the GUI and
    typically contains the NOAA API token.
    """

    geo_url = "https://nominatim.openstreetmap.org/search"
    geo_params = {"q": city, "format": "json", "limit": 1}
    # Nominatim requires a custom user agent with contact information
    geo_headers = {"User-Agent": "hh-tools/1.0 (https://example.com)"}
    try:
        r = requests.get(geo_url, params=geo_params, headers=geo_headers, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return []

    results = r.json()
    if not results:
        return []

    try:
        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return []
    extent = f"{lat-buffer},{lon-buffer},{lat+buffer},{lon+buffer}"
    params = {
        "datasetid": "GHCND",
        "datatypeid": "PRCP",
        "limit": limit,
        "extent": extent,
    }
    try:
        r = requests.get(STATION_URL, headers=headers, params=params, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return []

    data = r.json().get("results", [])
    return [
        {
            "id": st["id"],
            "name": st.get("name", ""),
            "latitude": st.get("latitude"),
            "longitude": st.get("longitude"),
            "mindate": st.get("mindate"),
            "maxdate": st.get("maxdate"),
            "datacoverage": st.get("datacoverage"),
        }
        for st in data
    ]


def available_datasets(
    station: str, token: str, *, timeout: int = 30
) -> List[dict[str, str]]:
    """Return dataset metadata available for ``station``.

    The function queries the NOAA ``datasets`` endpoint using the provided
    ``station`` identifier and returns a list of dictionaries.  Each dictionary
    contains the dataset ``id``, ``name`` and the earliest (``mindate``) and
    latest (``maxdate``) available dates.  The ``station`` may already include
    a dataset prefix; if not, it is used as-is which mirrors NOAA's behaviour.
    """

    headers = {"token": token}
    params = {"stationid": station, "limit": 1000}
    url = "https://www.ncdc.noaa.gov/cdo-web/api/v2/datasets"
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("results", [])
    return [
        {
            "id": d["id"],
            "name": d.get("name", ""),
            "mindate": d.get("mindate", ""),
            "maxdate": d.get("maxdate", ""),
        }
        for d in data
    ]


def available_datatypes(
    station: str, dataset: str, token: str, *, timeout: int = 30
) -> List[Tuple[str, str]]:
    """Return datatype identifiers and names for ``station`` and ``dataset``.

    The datatypes endpoint is queried with both the ``station`` and ``dataset``
    parameters which ensures that only datatypes relevant to the chosen dataset
    are returned.  A list of ``(id, name)`` tuples is provided.
    """

    stationid = station if ":" in station else f"{dataset}:{station}"
    headers = {"token": token}
    params = {"stationid": stationid, "datasetid": dataset, "limit": 1000}
    url = "https://www.ncdc.noaa.gov/cdo-web/api/v2/datatypes"
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("results", [])
    return [(d["id"], d.get("name", "")) for d in data]


def _write_tsf(path: Path, station: str, df: pd.DataFrame) -> None:
    with open(path, "w") as f:
        f.write(f"IDs:\t{station}\n")
        f.write("\n")
        f.write("Datetime\tRainfall\n")
        for _, row in df.iterrows():
            f.write(f"{row['Datetime']}\t{row['Rainfall']}\n")


def _write_swmm(path: Path, df: pd.DataFrame) -> None:
    with open(path, "w") as f:
        f.write("[TIMESERIES]\n")
        for _, row in df.iterrows():
            f.write(f"RAINFALL {row['Datetime']:%Y-%m-%d %H:%M} {row['Rainfall']}\n")


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--station", required=True, help="Station identifier")
    ap.add_argument("--start", required=True, help="Start date/time (YYYY-MM-DD or ISO)")
    ap.add_argument("--end", required=True, help="End date/time (YYYY-MM-DD or ISO)")
    ap.add_argument("--api-key", required=True, help="NOAA API token")
    ap.add_argument("--output", required=True, help="Output file path")
    ap.add_argument(
        "--format",
        choices=["csv", "tsf", "swmm"],
        default="csv",
        help="Output format",
    )
    ap.add_argument(
        "--units", choices=["mm", "in"], default="mm", help="Units for rainfall values"
    )
    ap.add_argument("--source", default="noaa", help="Data source identifier")
    ap.add_argument("--dataset", default="GHCND", help="NOAA dataset identifier")
    ap.add_argument("--datatype", default="PRCP", help="NOAA datatype identifier")
    ap.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    args = ap.parse_args(list(argv) if argv is not None else None)

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.ERROR
    logging.basicConfig(level=level, format="%(message)s")

    url = NOAA_URL if args.source.lower() == "noaa" else "https://example.com/rainfall"
    df = fetch_rainfall(
        args.station,
        args.start,
        args.end,
        args.api_key,
        url=url,
        dataset=args.dataset,
        datatype=args.datatype,
        units=args.units,
    )

    out_path = Path(args.output)
    if out_path.suffix == "":
        out_path = out_path.with_suffix(f".{args.format}")

    if args.format == "csv":
        df.to_csv(out_path, index=False)
    elif args.format == "tsf":
        _write_tsf(out_path, args.station, df)
    else:  # swmm
        _write_swmm(out_path, df)

    logging.info(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

