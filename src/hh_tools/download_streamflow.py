#!/usr/bin/env python3
"""Utilities for downloading streamflow data from USGS NWIS.

The module provides a small wrapper around the USGS National Water
Information System (NWIS) API.  Results are normalised into a
``pandas.DataFrame`` with columns ``Datetime`` and ``Flow``.  The dataframe
can optionally be aggregated to a user specified time step and written to
CSV or TSF formats.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List

import pandas as pd
import requests
import logging

# Base NWIS URLs used by the helpers below
NWIS_URL = "https://waterservices.usgs.gov/nwis/iv/"
SITE_URL = "https://waterservices.usgs.gov/nwis/site/"


def fetch_streamflow(
    station: str,
    start: str,
    end: str,
    *,
    url: str = NWIS_URL,
    parameter: str = "00060",
    units: str = "cfs",
    timeout: int = 30,
) -> pd.DataFrame:
    """Fetch streamflow observations for ``station`` between ``start`` and ``end``.

    Parameters
    ----------
    station: str
        USGS station identifier.
    start, end: str
        ISO date/time strings accepted by the NWIS API.
    url: str, optional
        Base URL to query; primarily used for tests.
    parameter: str, optional
        NWIS parameter code.  ``00060`` corresponds to discharge.
    units: str, optional
        Desired units for returned flow values.  ``cfs`` (cubic feet per
        second) is the NWIS default.  Passing ``m3/s`` converts the values to
        cubic metres per second.
    timeout: int, optional
        Network timeout in seconds.
    """

    params = {
        "format": "json",
        "sites": station,
        "startDT": start,
        "endDT": end,
        "parameterCd": parameter,
        "siteStatus": "all",
    }
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    series = data.get("value", {}).get("timeSeries", [])
    values: list[dict[str, str]] = []
    for ts in series:
        for block in ts.get("values", []):
            values.extend(block.get("value", []))
    if not values:
        raise ValueError("No streamflow data returned")

    df = pd.DataFrame(values)
    if {"dateTime", "value"} - set(df.columns):
        raise ValueError("Response missing 'value' field")

    df["Datetime"] = pd.to_datetime(df["dateTime"]).dt.tz_localize(None)
    df["Flow"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["Flow"])
    if units == "m3/s":
        df["Flow"] = df["Flow"] * 0.0283168
    return df[["Datetime", "Flow"]]


def aggregate_streamflow(df: pd.DataFrame, timestep: str | None) -> pd.DataFrame:
    """Aggregate ``df`` to ``timestep`` if provided.

    ``timestep`` follows pandas' resample notation (e.g. ``"1H"`` or
    ``"1D"``).  The mean value for each period is returned.  If
    ``timestep`` is ``None`` the dataframe is returned unchanged.
    """

    if not timestep:
        return df
    return df.set_index("Datetime").resample(timestep).mean().reset_index()


def search_stations(
    query: str, *, parameter: str = "00060", timeout: int = 30
) -> pd.DataFrame:
    """Search for USGS stations whose name contains ``query``.

    Returns a :class:`pandas.DataFrame` with columns ``id`` and ``name``.
    ``parameter`` filters stations to those providing the desired NWIS
    parameter code.
    """

    params = {
        "format": "json",
        "siteName": query,
        "parameterCd": parameter,
        "siteType": "ST",
    }
    r = requests.get(SITE_URL, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("value", {}).get("sites", [])
    records = []
    for st in data:
        code = (st.get("siteCode") or [{}])[0].get("value")
        name = st.get("siteName", "")
        if not code or not name:
            continue
        if query.lower() in name.lower() or query.lower() in code.lower():
            records.append({"id": code, "name": name})
    if not records:
        return pd.DataFrame(columns=["id", "name"])
    return pd.DataFrame.from_records(records)


def find_stations_by_city(
    city: str,
    *,
    parameter: str = "00060",
    buffer: float = 0.25,
    timeout: int = 30,
    limit: int = 100,
) -> List[dict[str, object]]:
    """Locate stations near ``city`` using a simple bounding box search."""

    geo_url = "https://nominatim.openstreetmap.org/search"
    geo_params = {"q": city, "format": "json", "limit": 1}
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

    bbox = f"{lon-buffer},{lat-buffer},{lon+buffer},{lat+buffer}"
    params = {
        "format": "json",
        "bBox": bbox,
        "parameterCd": parameter,
        "siteType": "ST",
    }
    try:
        r = requests.get(SITE_URL, params=params, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return []

    sites = r.json().get("value", {}).get("sites", [])[:limit]
    data = []
    for st in sites:
        code = (st.get("siteCode") or [{}])[0].get("value")
        name = st.get("siteName", "")
        if not code or not name:
            continue
        st_lat = st.get("geoLocation", {}).get("geogLocation", {}).get("latitude")
        st_lon = st.get("geoLocation", {}).get("geogLocation", {}).get("longitude")
        data.append({
            "id": code,
            "name": name,
            "latitude": st_lat,
            "longitude": st_lon,
        })
    return data


def _write_tsf(path: Path, station: str, df: pd.DataFrame) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"IDs:\t{station}\n")
        f.write("\n")
        f.write("Date/Time\tFlow\n")
        for _, row in df.iterrows():
            f.write(f"{row['Datetime']:%m/%d/%Y %H:%M}\t{row['Flow']}\n")


def _write_swmm(path: Path, df: pd.DataFrame) -> None:
    with open(path, "w") as f:
        f.write("[TIMESERIES]\n")
        for _, row in df.iterrows():
            f.write(f"FLOW {row['Datetime']:%Y-%m-%d %H:%M} {row['Flow']}\n")


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--station", required=True, help="USGS station identifier")
    ap.add_argument("--start", required=True, help="Start date/time (YYYY-MM-DD or ISO)")
    ap.add_argument("--end", required=True, help="End date/time (YYYY-MM-DD or ISO)")
    ap.add_argument("--output", required=True, help="Output file path")
    ap.add_argument(
        "--format",
        choices=["csv", "tsf", "swmm"],
        default="csv",
        help="Output file format",
    )
    ap.add_argument("--parameter", default="00060", help="NWIS parameter code")
    ap.add_argument(
        "--units", choices=["cfs", "m3/s"], default="cfs", help="Units for flow values"
    )
    ap.add_argument(
        "--timestep", help="Optional aggregation timestep e.g. 'H' or '1D'"
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    args = ap.parse_args(list(argv) if argv is not None else None)

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.ERROR
    logging.basicConfig(level=level, format="%(message)s")

    df = fetch_streamflow(
        args.station,
        args.start,
        args.end,
        parameter=args.parameter,
        units=args.units,
    )
    df = aggregate_streamflow(df, args.timestep)

    out_path = Path(args.output)
    if out_path.suffix == "":
        out_path = out_path.with_suffix(f".{args.format}")

    if args.format == "csv":
        df.to_csv(out_path, index=False)
    elif args.format == "tsf":
        _write_tsf(out_path, args.station, df)
    else:
        _write_swmm(out_path, df)

    logging.info(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
