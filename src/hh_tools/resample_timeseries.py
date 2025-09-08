#!/usr/bin/env python3
"""Resample time series to a new timestep with export and plotting options."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from .extract_timeseries import file_export_dat, file_export_tsf

# ---------------------------------------------------------------------------
# Core functionality
# ---------------------------------------------------------------------------

def load_series(path: str, column: str | None = None) -> pd.Series:
    """Load a time series from *path* using *column* if provided."""
    df = pd.read_csv(path)
    if df.empty:
        return pd.Series(dtype="float64")
    time_col = df.columns[0]
    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col).sort_index()
    if column and column in df.columns:
        return df[column].astype(float)
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            return df[c].astype(float)
    raise ValueError("No numeric column found in input file")


def resample_series(series: pd.Series, freq: str, method: str) -> pd.Series:
    """Return *series* resampled to *freq* using *method*."""
    return getattr(series.resample(freq), method)()


def percent_error(original: pd.Series, resampled: pd.Series) -> float:
    """Compute percent error between original and resampled totals."""
    if original.empty:
        return 0.0
    orig_total = original.sum()
    if orig_total == 0:
        return 0.0
    aligned = resampled.reindex(original.index, method="nearest")
    res_total = aligned.sum()
    return abs(res_total - orig_total) / abs(orig_total) * 100.0


def export_series(series: pd.Series, path: Path, fmt: str) -> None:
    """Export *series* to *path* in *fmt* format."""
    df = series.to_frame(name=series.name or "value")
    if fmt == "csv":
        df.to_csv(path, index=True)
    elif fmt == "dat":
        header = f"IDs:\t{path.stem}\nDate/Time\t{df.columns[0]}"
        file_export_dat(df, str(path), header, "%Y-%m-%d %H:%M:%S", "%.6g")
    elif fmt == "tsf":
        header1 = f"IDs:\t{path.stem}"
        header2 = "Date/Time\t" + df.columns[0]
        file_export_tsf(df, str(path), header1, header2, "%Y-%m-%d %H:%M:%S", "%.6g")
    else:
        raise ValueError(f"Unknown format: {fmt}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("input", help="Input CSV file with time and value columns")
    p.add_argument("--column", help="Column name with values (default: first numeric)")
    p.add_argument("--freq", required=True, help="New time step (e.g. '30min', '1H')")
    p.add_argument(
        "--method",
        choices=["mean", "sum", "median", "max", "min"],
        default="mean",
        help="Resampling aggregation method",
    )
    p.add_argument(
        "--output",
        help="Output file path; defaults to '<input>_resampled.<format>'",
    )
    p.add_argument(
        "--format", choices=["csv", "dat", "tsf"], default="csv", help="Output format"
    )
    p.add_argument(
        "--plot",
        action="store_true",
        help="Show preview plot of original and resampled data",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Increase logging verbosity")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress informational logs")
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
    resampled = resample_series(series, args.freq, args.method)
    err = percent_error(series, resampled)
    logging.info(f"Percent difference in totals: {err:.2f}%")

    base = Path(args.input)
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = base.with_name(base.stem + f"_resampled.{args.format}")
    export_series(resampled, out_path, args.format)

    if args.plot:
        import matplotlib.pyplot as plt

        plt.figure()
        plt.plot(series.index, series.values, label="Original")
        plt.plot(resampled.index, resampled.values, label="Resampled")
        plt.legend()
        plt.tight_layout()
        plt.show()

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
