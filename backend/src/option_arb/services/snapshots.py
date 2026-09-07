"""Shared gating for per-opportunity evolution snapshots.

Both the 1:1 `Screener` and the `StructuredScreener` keep a time series of an
opportunity's economics. To bound row growth they only append a snapshot when
something material changed. This module is the single definition of "material".
"""

from __future__ import annotations

from datetime import UTC, datetime


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def should_snapshot(
    *,
    last_snapshot_at: datetime | None,
    last_value: float | None,
    new_value: float,
    now: datetime,
    min_interval_sec: float,
    delta: float,
    extra_trigger: bool = False,
) -> bool:
    """True when a new snapshot is due.

    - `last_snapshot_at is None` → first snapshot, always.
    - `>= min_interval_sec` since the last one → yes (keeps a baseline cadence).
    - headline value moved by `>= delta` → yes.
    - `extra_trigger` → yes (e.g. the winning venue mix changed).
    """
    if last_snapshot_at is None:
        return True
    if (now - _aware(last_snapshot_at)).total_seconds() >= min_interval_sec:
        return True
    if last_value is None or abs(new_value - last_value) >= delta:
        return True
    return extra_trigger
