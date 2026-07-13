from datetime import datetime, timedelta

from .contracts.enums import TimePreset
from .contracts.requests import TimeRangeQuery


def resolve_time_range(query: TimeRangeQuery, *, now: datetime) -> tuple[datetime, datetime]:
    if query.time_preset is TimePreset.CUSTOM:
        if query.from_ is None or query.to is None:
            raise ValueError("CUSTOM requires from and to")
        return query.from_, query.to
    durations = {
        TimePreset.LATEST_15M: timedelta(minutes=15),
        TimePreset.LATEST_1H: timedelta(hours=1),
        TimePreset.LATEST_24H: timedelta(hours=24),
        TimePreset.LATEST_7D: timedelta(days=7),
    }
    return now - durations[query.time_preset], now
