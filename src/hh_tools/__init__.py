"""Hydrology and hydraulics tooling with CLI and GUI interfaces."""

import os

# Avoid numexpr warning about thread count; default to 8 threads unless
# explicitly overridden by the user environment.
os.environ.setdefault("NUMEXPR_MAX_THREADS", "8")

# Import heavy modules lazily to avoid pulling in optional dependencies at
# import time.  The ``*_main`` helpers simply forward to the respective module
# when invoked.

def extract_timeseries_main(*args, **kwargs):  # pragma: no cover - thin wrapper
    from .extract_timeseries import main
    return main(*args, **kwargs)


def review_flow_data_main(*args, **kwargs):  # pragma: no cover - thin wrapper
    from .review_flow_data import main
    return main(*args, **kwargs)


def design_storm_main(*args, **kwargs):  # pragma: no cover - thin wrapper
    from .design_storm import main
    return main(*args, **kwargs)


def sensitivity_main(*args, **kwargs):  # pragma: no cover - thin wrapper
    from .sensitivity import main
    return main(*args, **kwargs)


def resample_timeseries_main(*args, **kwargs):  # pragma: no cover - thin wrapper
    from .resample_timeseries import main
    return main(*args, **kwargs)


__all__ = [
    "extract_timeseries_main",
    "review_flow_data_main",
    "design_storm_main",
    "sensitivity_main",
    "resample_timeseries_main",
]
