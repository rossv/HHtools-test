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
class MeterInfo:
    """Start and end timestamps for a meter during a dry event."""

    start: Optional[datetime] = None
    end: Optional[datetime] = None


@dataclass
class DryEvent:
    """Representation of a dry weather event.

    Attributes
    ----------
    start, end:
        Global start and end of the dry period.  These are computed from the
        earliest meter start and latest meter end, respectively.
    meter_info:
        Mapping of meter name to :class:`MeterInfo` objects storing per-meter
        start and end times.
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    meter_info: Dict[str, MeterInfo] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON serialisable dictionary for the event."""

        def ts(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if isinstance(value, datetime) else None

        return {
            "start": ts(self.start),
            "end": ts(self.end),
            "meters": {
                meter: {"start": ts(info.start), "end": ts(info.end)}
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
            dv.meter_info[meter] = MeterInfo(start=start, end=end)

        starts = [info.start for info in dv.meter_info.values() if info.start]
        ends = [info.end for info in dv.meter_info.values() if info.end]
        dv.start = min(starts) if starts else None
        dv.end = max(ends) if ends else None
        events.append(dv)

    return events


def events_to_json(events: List[DryEvent]) -> str:
    """Serialize a list of :class:`DryEvent` objects to JSON.

    The resulting JSON contains the global start/end and per-meter start/end
    for each event.
    """

    return json.dumps([ev.to_dict() for ev in events], indent=2)
