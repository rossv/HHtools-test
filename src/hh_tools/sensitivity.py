#!/usr/bin/env python3
"""Perform simple sensitivity analysis by sweeping SWMM input parameters.

The base ``.inp`` file may contain placeholders using :class:`string.Template`
syntax (e.g. ``$param``). Parameter ranges are provided via a JSON or YAML
file mapping parameter names to lists of values.  For each combination of
parameters the input file is rendered, SWMM is executed and requested output
metrics are collected.  The results are compiled into a summary table and
optional PNG plots.
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from itertools import product
from pathlib import Path
from string import Template
from typing import Any, Callable, Dict, Iterable, Sequence

import pandas as pd

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except Exception:  # pragma: no cover - noqa: BLE001
    yaml = None  # type: ignore


# ---------------------------------------------------------------------------
# Parameter handling
# ---------------------------------------------------------------------------

def load_param_ranges(path: Path) -> Dict[str, list[Any]]:
    """Load parameter ranges from JSON or YAML file at *path*."""
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:  # pragma: no cover - depends on environment
            raise RuntimeError("YAML parameter file provided but PyYAML not installed")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):  # pragma: no cover - invalid user input
        raise ValueError("Parameter file must define a mapping")
    return {str(k): list(v) for k, v in data.items()}


def iter_parameter_sets(ranges: Dict[str, list[Any]]) -> Iterable[Dict[str, Any]]:
    """Yield dictionaries for each parameter combination in *ranges*."""
    keys = list(ranges)
    for values in product(*ranges.values()):
        yield dict(zip(keys, values))


def render_inp(base_inp: Path, params: Dict[str, Any]) -> Path:
    """Return path to temporary ``.inp`` with *params* substituted."""
    text = base_inp.read_text()
    rendered = Template(text).safe_substitute(params)
    tmpdir = tempfile.mkdtemp()
    new_path = Path(tmpdir) / "model.inp"
    new_path.write_text(rendered)
    return new_path


# ---------------------------------------------------------------------------
# SWMM execution helper
# ---------------------------------------------------------------------------

def run_swmm(inp_file: Path, metrics: Sequence[str], swmm_exe: str = "swmm5") -> Dict[str, float]:
    """Execute SWMM for *inp_file* and compute *metrics*.

    This routine requires the external ``swmm5`` executable and the
    ``swmmtoolbox`` Python package.  Only very coarse metrics are supported
    (``peak_flow`` and ``runoff_volume``).  The function is primarily intended
    as a default implementation and is easily mocked during testing.
    """

    try:  # pragma: no cover - heavy runtime dependency
        import subprocess
        import swmmtoolbox.swmmtoolbox as swmm  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("SWMM execution requires swmm5 and swmmtoolbox") from exc

    with tempfile.TemporaryDirectory() as tmpdir:
        rpt = Path(tmpdir) / "run.rpt"
        out = Path(tmpdir) / "run.out"
        cmd = [swmm_exe, str(inp_file), str(rpt), str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
        results: Dict[str, float] = {}
        if "peak_flow" in metrics:
            df = pd.DataFrame(swmm.extract(str(out), ["system", "", "Flow_rate"]))
            if not df.empty:
                results["peak_flow"] = float(df.max().iloc[0])
        if "runoff_volume" in metrics:
            df = pd.DataFrame(swmm.extract(str(out), ["subcatchment", "", "Total_runoff"]))
            if not df.empty:
                results["runoff_volume"] = float(df.sum().iloc[0])
        return results


# ---------------------------------------------------------------------------
# Main analysis routine
# ---------------------------------------------------------------------------

def sensitivity_analysis(
    base_inp: Path,
    param_ranges: Dict[str, list[Any]],
    metrics: Sequence[str],
    swmm_exe: str = "swmm5",
    make_plots: bool = False,
    plot_dir: Path | None = None,
    runner: Callable[[Path, Sequence[str], str], Dict[str, float]] | None = None,
) -> pd.DataFrame:
    """Run sensitivity analysis and return a DataFrame of results."""

    if runner is None:
        runner = run_swmm

    records: list[Dict[str, Any]] = []
    for params in iter_parameter_sets(param_ranges):
        inp_path = render_inp(base_inp, params)
        results = runner(inp_path, metrics, swmm_exe)
        records.append({**params, **results})
    df = pd.DataFrame(records)

    if make_plots and plot_dir is not None and not df.empty:
        try:  # pragma: no cover - optional plotting
            import matplotlib.pyplot as plt  # type: ignore
        except Exception:  # pragma: no cover - no matplotlib
            plt = None  # type: ignore
        if plt is not None:
            plot_dir.mkdir(parents=True, exist_ok=True)
            xcols = list(param_ranges.keys())
            for metric in metrics:
                if metric in df.columns:
                    ax = df.plot(x=xcols[0] if len(xcols) == 1 else None, y=metric)
                    ax.figure.savefig(plot_dir / f"{metric}.png")
                    plt.close(ax.figure)
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("inp", help="Base SWMM .inp file with parameter placeholders")
    p.add_argument("--params", required=True, help="JSON/YAML file with parameter ranges")
    p.add_argument(
        "--metrics",
        required=True,
        help="Comma-separated output metrics to compute (e.g. peak_flow,runoff_volume)",
    )
    p.add_argument("--output", default="sensitivity_results.csv", help="Output CSV path")
    p.add_argument("--swmm", default="swmm5", help="SWMM executable path")
    p.add_argument("--plot", help="Directory to save PNG plots")
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

    param_ranges = load_param_ranges(Path(args.params))
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
    plot_dir = Path(args.plot) if args.plot else None

    df = sensitivity_analysis(
        Path(args.inp),
        param_ranges,
        metrics,
        swmm_exe=args.swmm,
        make_plots=bool(plot_dir),
        plot_dir=plot_dir,
    )
    df.to_csv(args.output, index=False)
    logging.info(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
