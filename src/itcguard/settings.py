"""Reconciliation settings with explicit, testable defaults."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import as_decimal


@dataclass(frozen=True, slots=True)
class ReconciliationSettings:
    """Tolerance and matching controls used by the deterministic engine."""

    amount_tolerance: Decimal = Decimal("1.00")
    max_edit_distance: int = 2
    date_tolerance_days: int = 0

    def __post_init__(self) -> None:
        tolerance = as_decimal(self.amount_tolerance, field_name="amount_tolerance")
        if tolerance < 0:
            raise ValueError("amount_tolerance must not be negative")
        if self.max_edit_distance < 0:
            raise ValueError("max_edit_distance must not be negative")
        if self.date_tolerance_days < 0:
            raise ValueError("date_tolerance_days must not be negative")
        object.__setattr__(self, "amount_tolerance", tolerance)
