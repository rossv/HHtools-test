from __future__ import annotations

"""Utilities for extracting dry weather events from meter data.

This module exposes a :func:`detect_dry_events` function that merges dry
periods from individual meters into global events while tracking the start and
end times for each meter.  The resulting :class:`DryEvent` objects can be
exported to JSON with per-meter start/end information to enable analysis of
meter specific dry weather flow (DWF) durations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Tuple, Optional
import json


@dataclass
class MeterEvent:
    """Per-meter information for an event.

    Parameters
    ----------
    start, end:
        Timestamps bounding the event for the given meter.
    volume:
        Integrated event volume above ``base_flow``.  Units depend on the
        provided flow values (e.g. ``ft^3`` or ``m^3``).
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    volume: float = 0.0


@dataclass
class DryEvent:
    """Representation of a dry weather event.

    Attributes
    ----------
    start, end:
        Global start and end of the dry period.  These are computed from the
        earliest meter start and latest meter end, respectively.
    meter_info:
        Mapping of meter name to :class:`MeterEvent` objects storing per-meter
        start, end and volume information.
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    meter_info: Dict[str, MeterEvent] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON serialisable dictionary for the event."""

        def ts(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if isinstance(value, datetime) else None

        return {
            "start": ts(self.start),
            "end": ts(self.end),
            "meters": {
                meter: {
                    "start": ts(info.start),
                    "end": ts(info.end),
                    "volume": info.volume,
                }
                for meter, info in self.meter_info.items()
            },
        }


def detect_dry_events(
    meter_periods: Dict[str, Iterable[Tuple[datetime, datetime]]]
) -> List[DryEvent]:
    """Combine per-meter dry periods into :class:`DryEvent` objects.

    Parameters
    ----------
    meter_periods:
        Mapping of meter name to an iterable of ``(start, end)`` tuples
        representing dry weather periods for that meter.

    Returns
    -------
    list[DryEvent]
        A list of merged dry events.  Each event contains global start/end
        timestamps as well as meter specific information in ``meter_info``.
    """

    events: List[DryEvent] = []
    if not meter_periods:
        return events

    meter_lists: Dict[str, List[Tuple[datetime, datetime]]] = {
        m: list(p) for m, p in meter_periods.items()
    }

    first_meter = next(iter(meter_lists))
    num_events = len(meter_lists[first_meter])

    for idx in range(num_events):
        dv = DryEvent()
        for meter, periods in meter_lists.items():
            if idx >= len(periods):
                continue
            start, end = periods[idx]
            dv.meter_info[meter] = MeterEvent(start=start, end=end)

        starts = [info.start for info in dv.meter_info.values() if info.start]
        ends = [info.end for info in dv.meter_info.values() if info.end]
        dv.start = min(starts) if starts else None
        dv.end = max(ends) if ends else None
        events.append(dv)

    return events


def populate_meter_info(
    events: List[DryEvent],
    meter_series: Dict[str, Iterable[Tuple[datetime, float]]],
    base_flows: Dict[str, float],
) -> None:
    """Populate per-meter volume information for detected events.

    Parameters
    ----------
    events:
        Events returned from :func:`detect_dry_events`.
    meter_series:
        Mapping of meter name to an iterable of ``(timestamp, flow)`` tuples.
        The series should cover the period of interest and be ordered by time.
    base_flows:
        Mapping of meter name to a base flow value used to compute excess
        volume.  If a meter is missing from this mapping, a base flow of ``0``
        is assumed.

    Notes
    -----
    The integration uses a simple left-hand Riemann sum where ``dt`` is the
    time in seconds between consecutive samples and only positive ``flow -
    base_flow`` values are accumulated.
    """

    series = {m: sorted(list(s)) for m, s in meter_series.items()}

    for event in events:
        for meter, info in event.meter_info.items():
            if meter not in series:
                continue

            base = base_flows.get(meter, 0.0)
            readings = [r for r in series[meter] if info.start <= r[0] <= info.end]
            if len(readings) < 2:
                info.volume = 0.0
                continue

            volume = 0.0
            prev_time, prev_flow = readings[0]
            for ts, flow in readings[1:]:
                dt = (ts - prev_time).total_seconds()
                excess = max(prev_flow - base, 0.0)
                volume += excess * dt
                prev_time, prev_flow = ts, flow

            info.volume = volume


def export_to_json(events: List[DryEvent]) -> str:
    """Serialize a list of :class:`DryEvent` objects to JSON including volume."""

    return json.dumps([ev.to_dict() for ev in events], indent=2)
