#!/usr/bin/env python3
"""Parameter calibration for SWMM models.

This module provides a thin wrapper around :mod:`scipy.optimize` to adjust
model parameters so that simulated results match observed data.  Only a very
small subset of SWMM's capabilities is supported but the design allows the
``_run_swmm`` helper to be monkeypatched in tests.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple
import logging

import numpy as np
import pandas as pd
from scipy import optimize

from .sensitivity import render_inp

try:  # Optional dependency
    import yaml  # type: ignore
except Exception:  # pragma: no cover - noqa: BLE001
    yaml = None  # type: ignore


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def load_bounds(path: Path) -> Dict[str, Tuple[float, float]]:
    """Return parameter bounds from a JSON or YAML file."""

    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:  # pragma: no cover - depends on environment
            raise RuntimeError("YAML bounds file provided but PyYAML not installed")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):  # pragma: no cover - invalid input
        raise ValueError("Bounds file must define a mapping")
    bounds: Dict[str, Tuple[float, float]] = {}
    for key, val in data.items():
        if not isinstance(val, Sequence) or len(val) != 2:
            raise ValueError(f"Bounds for {key!r} must be a two-item sequence")
        bounds[str(key)] = (float(val[0]), float(val[1]))
    return bounds


# ---------------------------------------------------------------------------
# Metric utilities
# ---------------------------------------------------------------------------


def nash_sutcliffe(sim: np.ndarray, obs: np.ndarray) -> float:
    """Return the Nash–Sutcliffe efficiency."""

    return 1 - np.sum((obs - sim) ** 2) / np.sum((obs - np.mean(obs)) ** 2)


def rmse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Return the root mean squared error."""

    return float(np.sqrt(np.mean((sim - obs) ** 2)))


# ---------------------------------------------------------------------------
# SWMM runner (to be mocked during tests)
# ---------------------------------------------------------------------------


def _run_swmm(inp_file: Path, params: Dict[str, float], swmm_exe: str) -> pd.Series:
    """Execute SWMM for ``inp_file`` with ``params``.

    This default implementation merely raises an error as the real execution
    requires heavy external dependencies.  Tests should monkeypatch this
    function with a lightweight substitute returning a :class:`pandas.Series`
    of simulated values.
    """

    raise RuntimeError("SWMM execution not implemented; provide a mock _run_swmm")


# ---------------------------------------------------------------------------
# Calibration routine
# ---------------------------------------------------------------------------


def calibrate_model(
    base_inp: str | Path,
    bounds_file: str | Path,
    observed: str | Path,
    metric: str = "nse",
    swmm_exe: str = "swmm5",
) -> Tuple[Dict[str, float], optimize.OptimizeResult]:
    """Calibrate model parameters.

    Parameters
    ----------
    base_inp:
        Path to the base SWMM ``.inp`` file containing ``$placeholder``
        variables for each parameter.
    bounds_file:
        JSON or YAML file mapping parameter names to ``[low, high]`` bounds.
    observed:
        CSV file containing observed data; the first numeric column is used.
    metric:
        Error metric to minimise.  ``"nse"`` (Nash–Sutcliffe) aims to maximise
        efficiency while ``"rmse"`` minimises the root mean squared error.
    swmm_exe:
        Path to the SWMM executable.
    """

    base_inp = Path(base_inp)
    bounds_path = Path(bounds_file)
    obs_path = Path(observed)

    bounds = load_bounds(bounds_path)
    names = list(bounds)
    bnds = [bounds[n] for n in names]
    x0 = [np.mean(b) for b in bnds]

    obs_df = pd.read_csv(obs_path)
    num = obs_df.select_dtypes(include=["number"])
    if num.empty:
        raise ValueError("Observed data file must contain a numeric column")
    obs_series = num.iloc[:, 0].to_numpy(dtype=float)

    def objective(x: np.ndarray) -> float:
        params = dict(zip(names, x))
        inp = render_inp(base_inp, params)
        sim_series = _run_swmm(inp, params, swmm_exe)
        sim = np.asarray(sim_series, dtype=float)
        if metric == "nse":
            return 1 - nash_sutcliffe(sim, obs_series)
        if metric == "rmse":
            return rmse(sim, obs_series)
        raise ValueError(f"Unknown metric: {metric}")

    result = optimize.minimize(objective, x0, bounds=bnds, method="L-BFGS-B")
    best_params = dict(zip(names, result.x))
    return best_params, result


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("inp", help="Base SWMM .inp file with parameter placeholders")
    p.add_argument(
        "--bounds", required=True, help="JSON or YAML file with parameter bounds"
    )
    p.add_argument("--observed", required=True, help="CSV file with observed data")
    p.add_argument(
        "--metric", choices=["nse", "rmse"], default="nse", help="Calibration metric"
    )
    p.add_argument(
        "--output", required=True, help="Path to write calibrated parameters (JSON)"
    )
    p.add_argument("--swmm", default="swmm5", help="SWMM executable path")
    p.add_argument("--calibrated-inp", help="Write calibrated INP to this path")
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

    best, _res = calibrate_model(
        args.inp, args.bounds, args.observed, metric=args.metric, swmm_exe=args.swmm
    )
    Path(args.output).write_text(json.dumps(best, indent=2))
    logging.info(f"Wrote {args.output}")
    if args.calibrated_inp:
        inp_path = render_inp(Path(args.inp), best)
        shutil.copy(inp_path, args.calibrated_inp)
        logging.info(f"Wrote {args.calibrated_inp}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
