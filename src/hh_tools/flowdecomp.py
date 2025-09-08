#!/usr/bin/env python3
"""Decompose sanitary sewer flow into GWI, BWWF, and WWF.

This module provides a :class:`Decomposer` class which implements the core
logic along with a simple command line interface.  The implementation follows
the specification outlined in the project documentation but focuses on the
most common workflow:

* Uniform resampling and gap filling of input data.
* GWI handling either via a supplied time series or an average value with
  monthly multipliers.
* Dry weather detection based on recent rainfall totals.
* Estimation of weekday/weekend sanitary patterns.
* Residual wet weather flow calculation with optional RTK parameter fitting.

The RTK estimation uses a coarse differential evolution search followed by a
local optimisation.  The mathematical representation of the unit hydrograph
follows the triangular formulation used by the SWMM RDII model.  The goal of
this module is to provide a reproducible decomposition suitable for both CLI
and Python API use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import argparse
import json
import math
import sys

import numpy as np
import pandas as pd
from scipy import optimize

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DecompResult:
    """Container for decomposition outputs."""

    timeseries: pd.DataFrame
    parameters: dict

    def save(self, outdir: str | Path) -> None:
        """Write results to *outdir* as CSV/JSON."""
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        self.timeseries.to_csv(out / "timeseries.csv", index=False)
        with open(out / "parameters.json", "w", encoding="utf-8") as f:
            json.dump(self.parameters, f, indent=2)


# ---------------------------------------------------------------------------
# Core decomposition
# ---------------------------------------------------------------------------


class Decomposer:
    """Decompose flow into GWI, BWWF and WWF components."""

    def __init__(
        self,
        interval: str = "15min",
        tz: str = "UTC",
        gwi_mode: str = "timeseries",
        gwi_avg: float | None = None,
        gwi_monthly: Sequence[float] | None = None,
        dry_criteria: Optional[dict] = None,
        rtk_components: int = 0,
        optimize_method: str = "de_then_lbfgsb",
        clip_negative: bool = True,
    ) -> None:
        self.interval = pd.to_timedelta(interval)
        self.tz = tz
        self.gwi_mode = gwi_mode
        self.gwi_avg = gwi_avg
        self.gwi_monthly = list(gwi_monthly) if gwi_monthly else [1.0] * 12
        self.dry_criteria = dry_criteria or {"lookback_h": 48, "rain_thresh": 0.02}
        self.rtk_components = int(rtk_components)
        self.optimize_method = optimize_method
        self.clip_negative = clip_negative

    # ------------------------------------------------------------------
    def _resample(self, df: pd.DataFrame, col: str) -> pd.Series:
        s = (
            df.set_index("timestamp")[col]
            .sort_index()
            .asfreq(self.interval)
            .interpolate(limit=2)
        )
        return s

    # ------------------------------------------------------------------
    def _calc_gwi(self, flow_index: pd.DatetimeIndex, gwi_series: pd.Series | None) -> pd.Series:
        if self.gwi_mode == "timeseries":
            if gwi_series is None:
                raise ValueError("gwi_mode 'timeseries' requires gwi_df")
            gwi = gwi_series.reindex(flow_index).interpolate(limit_direction="both")
            if gwi.isna().any():
                if self.gwi_avg is None:
                    self.gwi_avg = float(gwi.mean())
                monthly = [self.gwi_avg * m for m in self.gwi_monthly]
                temp = pd.Series(index=flow_index, dtype=float)
                for m in range(1, 13):
                    temp[flow_index.month == m] = monthly[m - 1]
                gwi = gwi.fillna(temp)
            return gwi
        if self.gwi_avg is None:
            raise ValueError("gwi_avg must be provided for gwi_mode 'avg_monthly'")
        gwi = pd.Series(index=flow_index, dtype=float)
        for m in range(1, 13):
            gwi[flow_index.month == m] = self.gwi_avg * self.gwi_monthly[m - 1]
        return gwi

    # ------------------------------------------------------------------
    def _find_dry(self, rain: pd.Series | None, index: pd.DatetimeIndex) -> pd.Series:
        dry = pd.Series(True, index=index)
        if rain is None:
            return dry
        lookback = int(self.dry_criteria.get("lookback_h", 48) / (self.interval / pd.Timedelta("1H")))
        thresh = float(self.dry_criteria.get("rain_thresh", 0.02))
        accum = rain.fillna(0).rolling(lookback, min_periods=1).sum()
        dry = accum <= thresh
        return dry.reindex(index, fill_value=False)

    # ------------------------------------------------------------------
    def _calc_bwwf(self, flow: pd.Series, gwi: pd.Series, dry_mask: pd.Series) -> tuple[pd.Series, dict]:
        sanitary = (flow - gwi).where(dry_mask)
        df = sanitary.to_frame("sanitary")
        df["weekday"] = df.index.weekday
        df["hour"] = df.index.hour
        weekday_mask = df["weekday"] < 5
        weekend_mask = ~weekday_mask
        result = {}
        patterns = {}
        bwwf = pd.Series(index=flow.index, dtype=float)
        for mask, label in [(weekday_mask, "weekday"), (weekend_mask, "weekend")]:
            sub = df[mask & dry_mask]
            hourly = sub.groupby("hour")["sanitary"].mean().reindex(range(24), fill_value=0)
            daily_avg = sub["sanitary"].mean()
            if np.isfinite(daily_avg) and daily_avg > 0:
                norm = hourly / hourly.sum() if hourly.sum() else np.ones(24) / 24
                pattern = norm * daily_avg * 24
            else:
                pattern = pd.Series(np.zeros(24))
                norm = pattern
            patterns[f"{label}_hourly"] = list(pattern.values)
            result[f"daily_avg_{label}"] = float(daily_avg) if np.isfinite(daily_avg) else 0.0
            sub_idx = df.index[df["weekday"] < 5] if label == "weekday" else df.index[df["weekday"] >= 5]
            hour_idx = sub_idx.hour
            bwwf[sub_idx] = pattern.iloc[hour_idx].values
        return bwwf.ffill().bfill(), {**result, **patterns}

    # ------------------------------------------------------------------
    @staticmethod
    def _rtk_uh(R: float, T: float, K: float, interval_h: float) -> np.ndarray:
        tp = max(int(round(T / interval_h)), 1)
        L = int(round((1 + K) * tp))
        uh = np.zeros(L)
        for i in range(L):
            if i <= tp:
                uh[i] = i / tp
            else:
                uh[i] = max(1 - (i - tp) / (K * tp), 0)
        uh = uh / uh.sum()
        return R * uh

    # ------------------------------------------------------------------
    def _model_wwf(self, rain: np.ndarray, params: Sequence[float], interval_h: float) -> np.ndarray:
        n = len(params) // 3
        q = np.zeros(len(rain))
        for i in range(n):
            R, T, K = params[3 * i : 3 * (i + 1)]
            uh = self._rtk_uh(R, T, K, interval_h)
            q += np.convolve(rain, uh)[: len(rain)]
        return q

    # ------------------------------------------------------------------
    def fit(
        self,
        flow_df: pd.DataFrame,
        rain_df: pd.DataFrame | None = None,
        gwi_df: pd.DataFrame | None = None,
    ) -> DecompResult:
        flow = self._resample(flow_df, "flow").tz_localize(self.tz)
        rain = None
        if rain_df is not None:
            rain = self._resample(rain_df, "rain").reindex(flow.index, fill_value=0)
        gwi_series = None
        if gwi_df is not None:
            gwi_series = self._resample(gwi_df, "gwi").reindex(flow.index)
        gwi = self._calc_gwi(flow.index, gwi_series)
        dry_mask = self._find_dry(rain, flow.index)
        bwwf, pattern_params = self._calc_bwwf(flow, gwi, dry_mask)
        wwf = flow - gwi - bwwf
        if self.clip_negative:
            wwf = wwf.clip(lower=0)
        params: dict = {
            "gwi_mode": self.gwi_mode,
            "gwi_avg": self.gwi_avg,
            "gwi_monthly": self.gwi_monthly,
            **pattern_params,
        }
        if rain is not None and self.rtk_components:
            interval_h = self.interval / pd.Timedelta("1H")
            rain_arr = rain.values
            obs = wwf.values
            bounds = []
            for _ in range(self.rtk_components):
                bounds.extend([(0, 0.3), (0.25, 36.0), (0.2, 0.99)])
            def obj(p: np.ndarray) -> float:
                model = self._model_wwf(rain_arr, p, interval_h)
                return np.sum((obs - model) ** 2)
            result = optimize.differential_evolution(obj, bounds)
            opt = optimize.minimize(obj, result.x, bounds=bounds, method="L-BFGS-B")
            params["rtk_triplets"] = [
                {"R": opt.x[3 * i], "T_hours": opt.x[3 * i + 1], "K": opt.x[3 * i + 2]}
                for i in range(self.rtk_components)
            ]
            model = self._model_wwf(rain_arr, opt.x, interval_h)
            nse = 1 - np.sum((obs - model) ** 2) / np.sum((obs - obs.mean()) ** 2)
            params["fit_metrics"] = {"NSE": float(nse)}
            wwf = pd.Series(model, index=flow.index)
        df = pd.DataFrame({"timestamp": flow.index, "flow": flow.values, "gwi": gwi.values, "bwwf": bwwf.values, "wwf": wwf.values})
        if rain is not None:
            df["rainfall"] = rain.values
        return DecompResult(df, params)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", required=True, help="Flow CSV with 'timestamp' and 'flow' columns")
    parser.add_argument("--rain", help="Optional rainfall CSV with 'timestamp' and 'rain' columns")
    parser.add_argument("--gwi-ts", help="Optional GWI CSV with 'timestamp' and 'gwi' columns")
    parser.add_argument("--gwi-avg", type=float, help="Average GWI for mode 'avg_monthly'")
    parser.add_argument(
        "--gwi-monthly",
        help="Comma separated monthly multipliers",
    )
    parser.add_argument("--interval", default="15min", help="Resample interval, e.g. 15min")
    parser.add_argument("--tz", default="UTC", help="Timezone string")
    parser.add_argument("--rtk", type=int, default=0, help="Number of RTK triplets to fit")
    parser.add_argument("--out", default="out", help="Output directory")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    flow_df = pd.read_csv(args.flow, parse_dates=["timestamp"])
    rain_df = pd.read_csv(args.rain, parse_dates=["timestamp"]) if args.rain else None
    gwi_df = pd.read_csv(args.gwi_ts, parse_dates=["timestamp"]) if args.gwi_ts else None
    monthly = [float(v) for v in args.gwi_monthly.split(",")] if args.gwi_monthly else None
    dec = Decomposer(
        interval=args.interval,
        tz=args.tz,
        gwi_mode="timeseries" if gwi_df is not None else "avg_monthly",
        gwi_avg=args.gwi_avg,
        gwi_monthly=monthly,
        rtk_components=args.rtk,
    )
    result = dec.fit(flow_df, rain_df=rain_df, gwi_df=gwi_df)
    result.save(args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
