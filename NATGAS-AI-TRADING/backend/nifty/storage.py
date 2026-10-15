"""Replicated storage-surprise helper retained for schema parity; unused in NIFTY price-only mode."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageSignal:
    actual: float
    expected: float | None
    prior: float | None
    surprise: float | None
    week_over_week: float | None


def calculate_storage_signal(
    actual: float,
    *,
    expected: float | None = None,
    prior: float | None = None,
) -> StorageSignal:
    surprise = None if expected is None else actual - expected
    week_over_week = None if prior is None else actual - prior
    return StorageSignal(
        actual=actual,
        expected=expected,
        prior=prior,
        surprise=surprise,
        week_over_week=week_over_week,
    )
