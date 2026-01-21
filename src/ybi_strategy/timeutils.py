from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SessionTimes:
    tz: ZoneInfo
    trade_start: time
    trade_end: time
    force_flat: time

    def dt(self, d: date, t: time) -> datetime:
        return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, tzinfo=self.tz)


def parse_hhmm(value: str) -> time:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time: {value}")
    return time(int(parts[0]), int(parts[1]))

