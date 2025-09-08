#!/usr/bin/env python3
"""Review and clean flow-related time series data.

This tool loads tabular time series data from common formats (CSV, TSV,
Excel) and lets the user map columns to flow, depth and velocity
measurements. It checks for time step gaps, flags short lived spikes
("pops and drops"), optionally interpolates over those anomalies and
can down-sample to a coarser interval. The cleaned data are written to a
TSF file for use in other tools.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
from typing import Iterable, List

import pandas as pd

from .extract_timeseries import file_export_tsf


# ---------------------------------------------------------------------------
# Data loading and cleaning helpers
# ---------------------------------------------------------------------------

def load_dataframe(path: str, time_col: str) -> pd.DataFrame:
    """Load *path* into a DataFrame indexed by *time_col*.

    The format is auto-detected based on file extension. CSV/TSV files use
    pandas' Python engine to sniff delimiters while Excel files rely on
    :func:`pandas.read_excel`.
    """
    ext = pathlib.Path(path).suffix.lower()
    if ext in {".xls", ".xlsx"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=None, engine="python")
    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col).sort_index()
    return df

def find_time_step_issues(index: pd.DatetimeIndex) -> pd.Series:
    """Return a Series of irregular timestep differences."""
    diffs = index.to_series().diff().dropna()
    if diffs.empty:
        return diffs
    expected = diffs.mode().iloc[0]
    return diffs[diffs != expected]

def detect_spikes(series: pd.Series, threshold: float = 0.3) -> pd.Index:
    """Detect single-point spikes/drops in *series*.

    A point is considered a spike if it deviates from both neighbouring
    values by more than ``threshold`` times the larger neighbour and the
    neighbours roughly agree with each other.
    """
    anomalies: List[pd.Timestamp] = []
    s = series
    for i in range(1, len(s) - 1):
        prev, curr, nxt = s.iloc[i - 1], s.iloc[i], s.iloc[i + 1]
        base = max(abs(prev), abs(nxt), 1.0)
        if abs(curr - prev) > threshold * base and abs(nxt - prev) <= threshold * base:
            anomalies.append(s.index[i])
        elif abs(curr - nxt) > threshold * base and abs(prev - nxt) <= threshold * base:
            anomalies.append(s.index[i])
    return pd.Index(anomalies)

def clean_dataframe(df: pd.DataFrame, interpolate: bool, threshold: float) -> pd.DataFrame:
    """Replace detected spikes with NaN and optionally interpolate."""
    for col in df.columns:
        spikes = detect_spikes(df[col], threshold)
        if not spikes.empty:
            df.loc[spikes, col] = float("nan")
    if interpolate:
        df = df.interpolate(method="time")
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("input", help="Input CSV/TSV/Excel file")
    p.add_argument("--time-col", required=True, help="Name of timestamp column")
    p.add_argument("--flow-col", help="Column containing flow values")
    p.add_argument("--depth-col", help="Column containing depth values")
    p.add_argument("--velocity-col", help="Column containing velocity values")
    p.add_argument("--resample", help="Downsample frequency, e.g. '1H'")
    p.add_argument("--no-interpolate", action="store_true", help="Do not interpolate gaps/spikes")
    p.add_argument(
        "--spike-threshold",
        type=float,
        default=0.3,
        help="Fractional change defining a spike",
    )
    p.add_argument("--output", required=True, help="Output TSF file")
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase logging verbosity",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational logs",
    )
    return p.parse_args(list(argv) if argv is not None else None)

def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    log_level = logging.INFO
    if args.quiet:
        log_level = logging.WARNING
    if args.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    df = load_dataframe(args.input, args.time_col)

    cols = [c for c in [args.flow_col, args.depth_col, args.velocity_col] if c]
    if not cols:
        raise SystemExit("At least one of --flow-col/--depth-col/--velocity-col must be provided")
    df = df[cols]

    issues = find_time_step_issues(df.index)
    if not issues.empty:
        logging.info(f"Found {len(issues)} irregular time steps")

    df = clean_dataframe(df, not args.no_interpolate, args.spike_threshold)

    if args.resample:
        df = df.resample(args.resample).mean()

    df.index.name = "Datetime"
    header1 = "HH-Tools Flow Review"
    header2 = "Datetime\t" + "\t".join(df.columns)
    file_export_tsf(df, args.output, header1, header2, "%Y-%m-%d %H:%M:%S", "%.6g")
    logging.info(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
