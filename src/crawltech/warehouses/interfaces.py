"""Warehouse contract independent of the operational database implementation."""

from typing import Protocol


class Warehouse(Protocol):
    """Build and validate a trend-ready analytical dataset."""

    def build_trend_dataset(self, run_id: str) -> int: ...

    def validate_trend_dataset(self) -> bool: ...
