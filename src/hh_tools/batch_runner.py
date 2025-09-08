#!/usr/bin/env python3
"""Run multiple SWMM scenarios using :mod:`pyswmm`.

Scenarios may be described in a YAML/JSON configuration file or by passing
``.inp`` files directly on the command line.  Simulations are executed with
``pyswmm``'s embedded SWMM engine so no external executable is required.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
import logging

try:  # Optional YAML support
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML may be absent
    yaml = None  # type: ignore

try:  # Optional integration with summarize_outfiles
    from . import summarize_outfiles  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    summarize_outfiles = None  # type: ignore

try:  # Optional pyswmm dependency
    from pyswmm import Simulation  # type: ignore
except Exception:  # pragma: no cover - runtime dependency optional
    Simulation = None  # type: ignore


def load_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    """Return configuration dict and its base directory.

    Parameters
    ----------
    path:
        Path to a YAML or JSON configuration file.
    """
    cfg_path = Path(path)
    if str(cfg_path) == "-":
        text = sys.stdin.read()
        base_dir = Path.cwd()
        suffix = ""
    else:
        text = cfg_path.read_text(encoding="utf-8")
        base_dir = cfg_path.parent
        suffix = cfg_path.suffix.lower()
    if suffix in {".yml", ".yaml"}:
        if yaml is None:  # pragma: no cover - runtime dependency
            raise RuntimeError("PyYAML is required for YAML configs")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a mapping")
    return data, base_dir


def _apply_overrides(inp: Path, overrides: dict[str, Any], name: str) -> Path:
    """Return path to a temporary ``.inp`` with *overrides* applied."""
    if not overrides:
        return inp
    text = inp.read_text(encoding="utf-8")
    for key, value in overrides.items():
        pattern = re.compile(rf"^(\s*{re.escape(key)}\s+).*?$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda m, v=str(value): m.group(1) + v, text)
        else:
            text += f"\n{key}\t{value}"
    new_inp = inp.with_name(f"{inp.stem}_{re.sub(r'\W+', '_', name)}.inp")
    new_inp.write_text(text, encoding="utf-8")
    return new_inp
def run_batch(config: dict[str, Any], base_dir: Path) -> list[dict[str, Any]]:
    """Execute SWMM for each scenario in *config* using ``pyswmm``.

    The configuration must contain a ``scenarios`` list with entries specifying
    ``name`` and ``inp`` fields. Optional ``overrides`` dictionaries perform
    simple line-based substitutions within copied ``.inp`` files.
    """
    if Simulation is None:  # pragma: no cover - runtime dependency
        raise RuntimeError("pyswmm is required to run simulations")
    scenarios = config.get("scenarios", [])
    results: list[dict[str, Any]] = []
    for sc in scenarios:
        name = sc.get("name") or Path(sc["inp"]).stem
        inp = base_dir / sc["inp"]
        overrides = sc.get("overrides", {})
        run_inp = _apply_overrides(inp, overrides, name)
        out_path = run_inp.with_suffix(".out")
        try:
            # ``pyswmm`` changed the keyword arguments for report and output
            # files from ``rpt_file``/``out_file`` to ``reportfile``/``outputfile``
            # in version 2.0. Passing these paths positionally maintains
            # compatibility with both APIs.
            with Simulation(
                str(run_inp),
                str(run_inp.with_suffix(".rpt")),
                str(out_path),
            ) as sim:
                for _ in sim:
                    pass
            rc = 0
        except Exception as exc:  # pragma: no cover - error path
            rc = 1
            record_err = str(exc)
        record: dict[str, Any] = {
            "scenario": name,
            "status": "success" if rc == 0 else "error",
            "returncode": rc,
            "out_file": str(out_path),
        }
        if rc != 0:
            record["error"] = record_err
        if summarize_outfiles and rc == 0 and out_path.exists():
            try:
                metrics = summarize_outfiles.summarize(str(out_path))  # type: ignore[attr-defined]
                if isinstance(metrics, dict):
                    record.update(metrics)
            except Exception:
                pass  # Ignore summarization errors
        results.append(record)
    return results


def _write_log(records: list[dict[str, Any]], csv_path: Path, json_path: Path) -> None:
    """Write *records* to CSV and JSON files."""
    if not records:
        return
    fieldnames: set[str] = set()
    for rec in records:
        fieldnames.update(rec.keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sorted(fieldnames))
        writer.writeheader()
        writer.writerows(records)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Configuration file or one or more SWMM INP files",
    )
    parser.add_argument("--log-csv", default="batch_run_log.csv", help="CSV log path")
    parser.add_argument("--log-json", default="batch_run_log.json", help="JSON log path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.ERROR
    logging.basicConfig(level=level, format="%(message)s")
    first = args.paths[0]
    if first == "-" or Path(first).suffix.lower() in {".json", ".yml", ".yaml"}:
        config, base_dir = load_config(first)
    else:
        scenarios = [
            {"name": Path(p).stem, "inp": str(Path(p))} for p in args.paths
        ]
        config = {"scenarios": scenarios}
        base_dir = Path.cwd()
    records = run_batch(config, base_dir)
    _write_log(records, Path(args.log_csv), Path(args.log_json))
    for rec in records:
        line = f"{rec['scenario']}: {rec['status']} (rc={rec['returncode']})"
        if 'error' in rec:
            line += f" - {rec['error']}"
            logging.error(line)
        else:
            logging.info(line)
    return 0 if all(r["returncode"] == 0 for r in records) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
