#!/usr/bin/env python3
"""Validate SWMM ``.inp`` files for basic structural integrity.

This tool checks for required sections, numeric ranges, and cross references
between nodes and conduits in SWMM input files.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Iterable, Dict, List, Tuple


Issue = Dict[str, int | str]
Report = Dict[str, List[Issue] | str]


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------

def _parse_sections(path: str) -> Dict[str, List[Tuple[int, str]]]:
    sections: Dict[str, List[Tuple[int, str]]] = {}
    current: str | None = None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line.strip("[]").upper()
                sections.setdefault(current, [])
            else:
                sections.setdefault(current or "", []).append((lineno, line))
    return sections


def validate_file(path: str, *, check_ranges: bool = True, check_refs: bool = True) -> Report:
    sections = _parse_sections(path)
    errors: List[Issue] = []
    warnings: List[Issue] = []

    # Required sections
    required = ["JUNCTIONS", "OUTFALLS", "CONDUITS"]
    for sec in required:
        if sec not in sections:
            errors.append({"line": 0, "message": f"Missing [{sec}] section"})

    nodes: Dict[str, int] = {}
    for sec in ("JUNCTIONS", "OUTFALLS"):
        for lineno, line in sections.get(sec, []):
            parts = line.split()
            if not parts:
                continue
            node_id = parts[0]
            nodes[node_id] = lineno
            if check_ranges and sec == "JUNCTIONS":
                if len(parts) >= 3:
                    try:
                        depth = float(parts[2])
                        if depth < 0:
                            errors.append({"line": lineno, "message": "Negative maximum depth"})
                    except ValueError:
                        warnings.append({"line": lineno, "message": "Invalid depth value"})
                else:
                    warnings.append({"line": lineno, "message": "Incomplete junction record"})

    for lineno, line in sections.get("CONDUITS", []):
        parts = line.split()
        if len(parts) < 4:
            warnings.append({"line": lineno, "message": "Incomplete conduit record"})
            continue
        _, from_node, to_node, length_str = parts[:4]
        if check_refs:
            if from_node not in nodes or to_node not in nodes:
                errors.append({"line": lineno, "message": "Conduit references unknown node"})
        if check_ranges:
            try:
                length = float(length_str)
                if length <= 0:
                    errors.append({"line": lineno, "message": "Non-positive conduit length"})
            except ValueError:
                warnings.append({"line": lineno, "message": "Invalid conduit length"})

    return {"file": path, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("files", nargs="+", help="INP file(s) to validate")
    parser.add_argument(
        "--no-range",
        action="store_false",
        dest="check_ranges",
        help="Disable numeric range checks",
    )
    parser.add_argument(
        "--no-crossref",
        action="store_false",
        dest="check_refs",
        help="Disable cross-reference checks",
    )
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
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

    if not args.json:
        logging.info("Checking files: " + ", ".join(args.files))
        checks = ["required sections"]
        if args.check_ranges:
            checks.append("numeric ranges")
        if args.check_refs:
            checks.append("cross references")
        logging.info("Performing checks: " + ", ".join(checks))
    reports = [
        validate_file(f, check_ranges=args.check_ranges, check_refs=args.check_refs)
        for f in args.files
    ]

    if args.json:
        logging.info(json.dumps(reports, indent=2))
    else:
        for rep in reports:
            if not rep["errors"] and not rep["warnings"]:
                logging.info(f"{rep['file']}: OK")
                continue
            for issue in rep["errors"]:
                logging.error(
                    f"{rep['file']}:{issue['line']}: ERROR: {issue['message']}"
                )
            for issue in rep["warnings"]:
                logging.warning(
                    f"{rep['file']}:{issue['line']}: WARNING: {issue['message']}"
                )

    return 0 if all(not r["errors"] for r in reports) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
