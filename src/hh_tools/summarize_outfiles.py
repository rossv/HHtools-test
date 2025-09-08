#!/usr/bin/env python3
"""Summarize SWMM `.out` files with basic statistics.

This module provides a command line interface that extracts time series for
specified element IDs and parameters from one or more SWMM output files. For
each series it computes statistics including the peak value, mean value, total
volume (area under the curve) and time to peak. Results are written to a CSV
report for further analysis.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, List

import pandas as pd
from tqdm import tqdm

from .compare_outfiles import discover_ids, extract_series


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def summarize(
    outfiles: Iterable[str],
    item_type: str,
    ids: Iterable[str],
    params: Iterable[str],
    *,
    quiet: bool = False,
) -> list[dict[str, float | str]]:
    """Return summary statistics for provided ``outfiles``.

    Parameters
    ----------
    outfiles:
        Sequence of SWMM ``.out`` file paths.
    item_type:
        SWMM object type (e.g. ``node``, ``link``).
    ids:
        Iterable of element IDs to extract.
    params:
        Iterable of parameter names to summarize.
    quiet:
        If ``True`` progress bars are suppressed.
    """

    records: list[dict[str, float | str]] = []
    files = list(outfiles)
    ids_list = list(ids)
    params_list = list(params)
    total = len(files) * len(ids_list) * len(params_list)
    progress = tqdm(total=total, desc="Summarizing", unit="series", disable=quiet)
    for outfile in files:
        for element_id in ids_list:
            for param in params_list:
                df = extract_series(outfile, item_type, element_id, param)
                if df.empty:
                    progress.update(1)
                    continue
                peak = df["value"].max()
                mean = df["value"].mean()
                dt = df["Datetime"].diff().dt.total_seconds().fillna(0)
                total_volume = float((df["value"] * dt).sum())
                peak_time = df.loc[df["value"].idxmax(), "Datetime"]
                time_to_peak = float((peak_time - df["Datetime"].min()).total_seconds())
                records.append(
                    {
                        "file": outfile,
                        "id": element_id,
                        "param": param,
                        "peak": peak,
                        "mean": mean,
                        "total_volume": total_volume,
                        "time_to_peak": time_to_peak,
                    }
                )
                progress.update(1)
    progress.close()
    return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("files", nargs="+", help="SWMM .out files to summarize")
    parser.add_argument(
        "--type",
        default="node",
        choices=["node", "link", "subcatchment", "system"],
        help="SWMM object type to summarize",
    )
    parser.add_argument(
        "--ids",
        default="ALL",
        help="Comma-separated element IDs to include (or ALL)",
    )
    parser.add_argument(
        "--params",
        default="Flow_rate",
        help="Comma-separated parameter names to summarize",
    )
    parser.add_argument(
        "--output",
        default="summary_report.csv",
        help="Output CSV report path",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase logging verbosity",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational logs",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    log_level = logging.INFO
    if args.quiet:
        log_level = logging.WARNING
    if args.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    if len(ids) == 1 and ids[0].upper() == "ALL":
        discovered: set[str] = set()
        for outfile in args.files:
            discovered.update(discover_ids(outfile, args.type))
        ids = sorted(discovered)

    params = [p.strip() for p in args.params.split(",") if p.strip()]

    records = summarize(args.files, args.type, ids, params, quiet=args.quiet)
    if records:
        df = pd.DataFrame.from_records(records)
        out_path = Path(args.output)
        df.to_csv(out_path, index=False)
        logging.info(f"Wrote report with {len(df)} rows to {out_path}")
    else:
        logging.error("No data summarized; check inputs.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
