#!/usr/bin/env python3
"""Extract rainfall or flow events based on intensity and duration thresholds."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, List

import pandas as pd


# ---------------------------------------------------------------------------
# Core functionality
# ---------------------------------------------------------------------------

def load_series(path: str, column: str | None = None) -> pd.Series:
    """Load a time series from *path* using *column* if provided.

    The file is assumed to be CSV with the first column representing time
    stamps. The first numeric column is used if *column* is not given.
    """
    df = pd.read_csv(path)
    if df.empty:
        return pd.Series(dtype="float64")
    time_col = df.columns[0]
    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col).sort_index()
    if column and column in df.columns:
        return df[column].astype(float)
    # pick first numeric column
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            return df[c].astype(float)
    raise ValueError("No numeric column found in input file")


def extract_events(
    series: pd.Series, threshold: float, min_duration: float
) -> List[pd.DataFrame]:
    """Return list of event DataFrames exceeding *threshold* for *min_duration* minutes."""
    if series.empty:
        return []
    mask = series >= threshold
    if not mask.any():
        return []
    groups = (mask != mask.shift()).cumsum()
    events: List[pd.DataFrame] = []
    step = series.index.to_series().diff().mode().iloc[0] if len(series) > 1 else pd.Timedelta(0)
    for gid, seg in series[mask].groupby(groups[mask]):
        start = seg.index[0]
        end = seg.index[-1]
        duration = end - start + step
        if duration.total_seconds() / 60.0 >= min_duration:
            events.append(seg.to_frame(name=series.name or "value"))
    return events


def export_events(
    events: List[pd.DataFrame], output_dir: Path, prefix: str = "event"
) -> List[Path]:
    """Write each event to *output_dir* as ``<prefix>_N.csv`` and return paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for i, df in enumerate(events, 1):
        path = output_dir / f"{prefix}_{i}.csv"
        df.to_csv(path, index=True, header=True)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("input", help="Input CSV file with time and value columns")
    p.add_argument("--column", help="Column name with values (default: first numeric)")
    p.add_argument("--threshold", type=float, required=True, help="Minimum value defining an event")
    p.add_argument(
        "--min-duration",
        type=float,
        default=0.0,
        help="Minimum event duration in minutes",
    )
    p.add_argument(
        "--output-dir",
        dest="outdir",
        default="events",
        help="Directory to write event files",
    )
    p.add_argument("--outdir", dest="outdir", help=argparse.SUPPRESS)
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

    series = load_series(args.input, args.column)
    events = extract_events(series, args.threshold, args.min_duration)
    prefix = Path(args.input).stem
    output_dir = Path(args.outdir)
    paths = export_events(events, output_dir, prefix=prefix)
    logging.info(f"Extracted {len(paths)} events to {output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
