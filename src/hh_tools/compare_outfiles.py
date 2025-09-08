#!/usr/bin/env python3
"""Compare two SWMM ``.out`` files and report time series differences.

The tool extracts specified element IDs and parameters from two output files
and computes simple statistics (maximum and mean absolute difference).
Results are written to a CSV report for easy review.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, List

import pandas as pd
from tqdm import tqdm

# Re-use discovery logic from extract_timeseries for consistency
from hh_tools.extract_timeseries import discover_ids as _discover_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def discover_ids(outfile: str, item_type: str) -> List[str]:
    """Discover element IDs of *item_type* present in *outfile*."""
    ids = _discover_ids(outfile, item_type)
    if item_type == "system" and not ids:
        return ["SYSTEM"]
    return ids


def extract_series(outfile: str, item_type: str, element_id: str, param: str) -> pd.DataFrame:
    """Extract a time series for *element_id* and *param* from *outfile*."""
    import swmmtoolbox.swmmtoolbox as swmm  # type: ignore

    try:
        name = "" if item_type == "system" else element_id
        data = swmm.extract(outfile, [item_type, name, param])
    except TypeError:
        logging.exception(
            "swmm.extract failed with list parameters; retrying with comma-separated string"
        )
        name = "" if item_type == "system" else element_id
        data = swmm.extract(outfile, f"{item_type},{name},{param}")
    df = pd.DataFrame(data).reset_index()
    if df.empty or df.shape[1] < 2:
        return pd.DataFrame(columns=["Datetime", "value"])
    df.columns = ["Datetime", "value"]
    return df


def compare_series(a: pd.DataFrame, b: pd.DataFrame) -> tuple[float, float]:
    """Return (max_abs_diff, mean_abs_diff) between two time series."""
    merged = a.merge(b, on="Datetime", how="inner", suffixes=("_1", "_2"))
    if merged.empty:
        return (float("nan"), float("nan"))
    diff = (merged["value_1"] - merged["value_2"]).abs()
    return diff.max(), diff.mean()


def build_diff_table(
    file1: str, file2: str, item_type: str, element_id: str, param: str
) -> pd.DataFrame:
    """Return a table of values and differences for the given series.

    Parameters
    ----------
    file1, file2:
        Paths to the SWMM ``.out`` files.
    item_type:
        SWMM object type (e.g. ``node``, ``link``).
    element_id:
        Element identifier within the files.
    param:
        Parameter name to extract.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns ``Datetime``, ``value_1``, ``value_2``, and
        ``diff`` where ``diff = value_1 - value_2``.
    """

    a = extract_series(file1, item_type, element_id, param)
    b = extract_series(file2, item_type, element_id, param)
    if a.empty or b.empty:
        return pd.DataFrame(columns=["Datetime", "value_1", "value_2", "diff"])
    merged = a.merge(b, on="Datetime", how="inner", suffixes=("_1", "_2"))
    if merged.empty:
        return pd.DataFrame(columns=["Datetime", "value_1", "value_2", "diff"])
    merged["diff"] = merged["value_1"] - merged["value_2"]
    return merged[["Datetime", "value_1", "value_2", "diff"]]


def plot_series(df: pd.DataFrame, param: str, path: Path) -> None:
    """Plot values from *df* and save to *path*.

    This function uses matplotlib but degrades silently if the library is not
    available. The plot shows both value columns and labels the y-axis with
    *param*.
    """

    try:  # pragma: no cover - matplotlib may be missing
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:  # pragma: no cover - handled gracefully
        logging.error("matplotlib not available; cannot create plot")
        return

    fig, ax = plt.subplots()
    ax.plot(pd.to_datetime(df["Datetime"]), df["value_1"], label="File 1")
    ax.plot(pd.to_datetime(df["Datetime"]), df["value_2"], label="File 2")
    ax.set_xlabel("Datetime")
    ax.set_ylabel(param)
    ax.legend()
    fig.autofmt_xdate()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("file1", help="First SWMM .out file")
    parser.add_argument("file2", help="Second SWMM .out file")
    parser.add_argument(
        "--type",
        default="node",
        choices=["node", "link", "subcatchment", "system"],
        help="SWMM object type to compare",
    )
    parser.add_argument(
        "--ids",
        default="ALL",
        help="Comma-separated element IDs to compare (or ALL)",
    )
    parser.add_argument(
        "--params",
        default="Flow_rate",
        help="Comma-separated parameter names to compare",
    )
    parser.add_argument(
        "--output",
        default="comparison_report.csv",
        help="Output CSV report path",
    )
    parser.add_argument(
        "--detailed-table",
        help="Optional CSV path to write detailed time series values and differences",
    )
    parser.add_argument(
        "--plot-dir",
        help="Optional directory to write PNG plots for each compared series",
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
        ids1 = discover_ids(args.file1, args.type)
        ids2 = discover_ids(args.file2, args.type)
        ids = sorted(set(ids1) & set(ids2))

    params = [p.strip() for p in args.params.split(",") if p.strip()]

    records: list[dict[str, float | str]] = []
    detailed_tables: list[pd.DataFrame] = []
    plot_dir = Path(args.plot_dir) if args.plot_dir else None
    if plot_dir is not None:
        plot_dir.mkdir(parents=True, exist_ok=True)
    total = len(ids) * len(params)
    progress = tqdm(total=total, desc="Comparing", unit="series", disable=args.quiet)
    for element_id in ids:
        for param in params:
            diff_df = build_diff_table(
                args.file1, args.file2, args.type, element_id, param
            )
            if diff_df.empty:
                progress.update(1)
                continue
            max_diff = diff_df["diff"].abs().max()
            mean_diff = diff_df["diff"].abs().mean()
            records.append(
                {
                    "id": element_id,
                    "param": param,
                    "max_abs_diff": max_diff,
                    "mean_abs_diff": mean_diff,
                }
            )
            if args.detailed_table:
                df_det = diff_df.copy()
                df_det["id"] = element_id
                df_det["param"] = param
                detailed_tables.append(
                    df_det[["id", "param", "Datetime", "value_1", "value_2", "diff"]]
                )
            if plot_dir is not None:
                plot_path = plot_dir / f"{element_id}_{param}.png"
                plot_series(diff_df, param, plot_path)
            progress.update(1)
    progress.close()

    if records:
        df = pd.DataFrame.from_records(records)
        df.to_csv(args.output, index=False)
        logging.info(f"Wrote report with {len(records)} rows to {args.output}")
        if args.detailed_table and detailed_tables:
            detailed = pd.concat(detailed_tables, ignore_index=True)
            detailed.to_csv(args.detailed_table, index=False)
            logging.info(
                f"Wrote detailed table with {len(detailed)} rows to {args.detailed_table}"
            )
    else:
        logging.error("No data compared; check IDs/parameters.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
