#!/usr/bin/env python3
"""Diff SWMM ``.inp`` files and report discrepancies.

This tool parses two SWMM input files, aligns records within each section,
and reports any lines that differ.  Differences can be written as a simple
CSV/table or emitted as JSON for downstream processing.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_sections(path: str) -> Dict[str, Dict[str, str]]:
    """Return mapping of section -> {key: value} for *path*.

    Lines beginning with ``;`` are ignored. Records are split on the first
    whitespace with the initial token treated as the key. Duplicate keys within
    a section are suffixed with ``#n`` to preserve all records.
    """

    sections: Dict[str, Dict[str, str]] = {}
    current: str | None = None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line.strip("[]").upper()
                sections.setdefault(current, {})
                continue
            if current is None:
                continue
            parts = line.split(None, 1)
            key = parts[0]
            value = parts[1] if len(parts) > 1 else ""
            if key in sections[current]:
                idx = 1
                new_key = f"{key}#{idx}"
                while new_key in sections[current]:
                    idx += 1
                    new_key = f"{key}#{idx}"
                key = new_key
            sections[current][key] = value
    return sections


def diff_inp(file1: str, file2: str) -> List[Dict[str, str | None]]:
    """Return a list of differences between two INP files."""

    sec1 = _parse_sections(file1)
    sec2 = _parse_sections(file2)
    diffs: List[Dict[str, str | None]] = []
    for section in sorted(set(sec1) | set(sec2)):
        items1 = sec1.get(section, {})
        items2 = sec2.get(section, {})
        keys = sorted(set(items1) | set(items2))
        for key in keys:
            val1 = items1.get(key)
            val2 = items2.get(key)
            if val1 != val2:
                diffs.append(
                    {
                        "section": section,
                        "id": key,
                        "file1": val1,
                        "file2": val2,
                    }
                )
    return diffs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("file1", help="First SWMM .inp file")
    parser.add_argument("file2", help="Second SWMM .inp file")
    parser.add_argument(
        "-o", "--output", help="Optional path to write table/JSON output"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output differences as JSON"
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

    diffs = diff_inp(args.file1, args.file2)

    if args.json:
        data = json.dumps(diffs, indent=2)
        if args.output:
            Path(args.output).write_text(data, encoding="utf-8")
        else:
            logging.info(data)
    else:
        df = pd.DataFrame(diffs)
        if df.empty:
            df = pd.DataFrame(columns=["section", "id", "file1", "file2"])
        else:
            df = df.fillna("")
        if args.output:
            df.to_csv(args.output, index=False)
        else:
            if df.empty:
                logging.info("No differences found.")
            else:
                logging.info(df.to_string(index=False))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
