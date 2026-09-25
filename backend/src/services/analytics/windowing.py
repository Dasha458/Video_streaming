"""
Period maths shared by every analytics query: where the current and
previous windows start, how a delta is expressed, and how a sparse daily
series is padded so days with no activity still appear.

Pure functions -- no session, no models -- so they are testable on their
own and the query code in service.py stays about SQL.
"""

from datetime import datetime, timedelta, timezone
from typing import Sequence

from src.schemas.analytics import DailyMetric, DeltaInt, Period


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _window(period: Period) -> tuple[datetime | None, datetime | None]:
    """
    Returns (current_since, previous_since).

    * current window: ``[current_since, now]``
    * previous window: ``[previous_since, current_since)``

    For ``Period.ALL`` both values are ``None`` (no time filter).
    """
    days = period.days
    if days is None:
        return None, None
    now = _now()
    current = now - timedelta(days=days)
    previous = now - timedelta(days=days * 2)
    return current, previous


def _pct_delta(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


def _delta(current: int, previous: int) -> DeltaInt:
    return DeltaInt(
        value=int(current),
        previous=int(previous),
        delta_percent=_pct_delta(int(current), int(previous)),
    )


def _fill_daily(rows: Sequence[tuple], since: datetime | None) -> list[DailyMetric]:
    """Ensure days with zero activity still appear in the series."""
    known = {str(r[0]): int(r[1]) for r in rows}
    if since is None:
        return [DailyMetric(date=d, count=c) for d, c in sorted(known.items())]
    out: list[DailyMetric] = []
    cursor = since.date()
    today = _now().date()
    while cursor <= today:
        key = cursor.isoformat()
        out.append(DailyMetric(date=key, count=known.get(key, 0)))
        cursor += timedelta(days=1)
    return out
