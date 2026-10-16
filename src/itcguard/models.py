"""Typed domain models shared by ingestion, matching, agents, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


def as_decimal(value: Any, *, field_name: str = "amount") -> Decimal:
    """Convert a money value without ever passing through binary floating point."""
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a decimal-compatible number")
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal amount") from exc


class InvoiceSource(StrEnum):
    BOOKS = "books"
    GSTR2B = "gstr2b"


class MatchStatus(StrEnum):
    MATCHED = "MATCHED"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    MISSING_IN_2B = "MISSING_IN_2B"
    MISSING_IN_BOOKS = "MISSING_IN_BOOKS"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    DUPLICATE = "DUPLICATE"


class MatchTier(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    AMOUNT_DATE = "amount_date"
    NONE = "none"


@dataclass(slots=True)
class Invoice:
    source: InvoiceSource
    row_id: str
    supplier_gstin: str
    supplier_name: str
    invoice_number_raw: str
    invoice_number_norm: str
    invoice_date: date
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    invoice_value: Decimal

    def __post_init__(self) -> None:
        if not self.row_id:
            raise ValueError("row_id must not be empty")
        if not self.supplier_gstin:
            raise ValueError("supplier_gstin must not be empty")
        if not self.invoice_number_norm:
            raise ValueError("invoice_number_norm must not be empty")
        if not isinstance(self.invoice_date, date):
            raise TypeError("invoice_date must be a datetime.date")
        for name in (
            "taxable_value",
            "igst",
            "cgst",
            "sgst",
            "cess",
            "invoice_value",
        ):
            setattr(self, name, as_decimal(getattr(self, name), field_name=name))

    @property
    def total_tax(self) -> Decimal:
        return self.igst + self.cgst + self.sgst + self.cess


@dataclass(slots=True)
class MatchResult:
    status: MatchStatus
    books_invoice: Invoice | None = None
    gstr2b_invoice: Invoice | None = None
    match_tier: MatchTier = MatchTier.NONE
    tax_difference: Decimal = Decimal("0")
    itc_at_risk: Decimal = Decimal("0")
    notes: list[str] = field(default_factory=list)
    explanation: str = ""
    confidence: Decimal | None = None
    resolver_suggestion: str | None = None
    human_confirmation_required: bool = False

    def __post_init__(self) -> None:
        self.tax_difference = as_decimal(self.tax_difference, field_name="tax_difference")
        self.itc_at_risk = as_decimal(self.itc_at_risk, field_name="itc_at_risk")
        if self.confidence is not None:
            self.confidence = as_decimal(self.confidence, field_name="confidence")


@dataclass(slots=True)
class ReconciliationReport:
    results: list[MatchResult] = field(default_factory=list)
    supplier_drafts: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    total_itc_at_risk: Decimal = Decimal("0")
    per_supplier_itc_at_risk: dict[str, Decimal] = field(default_factory=dict)
    confirmed_itc_at_risk: Decimal = Decimal("0")
    potential_itc_at_risk: Decimal = Decimal("0")
    per_supplier_confirmed_itc_at_risk: dict[str, Decimal] = field(default_factory=dict)
    per_supplier_potential_itc_at_risk: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.total_itc_at_risk = as_decimal(
            self.total_itc_at_risk,
            field_name="total_itc_at_risk",
        )
        self.per_supplier_itc_at_risk = {
            supplier: as_decimal(amount, field_name="supplier_itc_at_risk")
            for supplier, amount in self.per_supplier_itc_at_risk.items()
        }
        self.confirmed_itc_at_risk = as_decimal(self.confirmed_itc_at_risk, field_name="confirmed_itc_at_risk")
        self.potential_itc_at_risk = as_decimal(self.potential_itc_at_risk, field_name="potential_itc_at_risk")
        self.per_supplier_confirmed_itc_at_risk = {
            supplier: as_decimal(amount, field_name="supplier_confirmed_itc_at_risk")
            for supplier, amount in self.per_supplier_confirmed_itc_at_risk.items()
        }
        self.per_supplier_potential_itc_at_risk = {
            supplier: as_decimal(amount, field_name="supplier_potential_itc_at_risk")
            for supplier, amount in self.per_supplier_potential_itc_at_risk.items()
        }

    @classmethod
    def from_results(
        cls,
        results: list[MatchResult],
        supplier_drafts: dict[str, str] | None = None,
    ) -> "ReconciliationReport":
        counts: dict[str, int] = {}
        per_supplier: dict[str, Decimal] = {}
        per_supplier_confirmed: dict[str, Decimal] = {}
        per_supplier_potential: dict[str, Decimal] = {}
        confirmed = Decimal("0")
        potential = Decimal("0")
        for result in results:
            status = result.status.value
            counts[status] = counts.get(status, 0) + 1
            is_potential = result.status is MatchStatus.POSSIBLE_MATCH
            if is_potential:
                potential += result.itc_at_risk
            else:
                confirmed += result.itc_at_risk
            supplier = (result.books_invoice or result.gstr2b_invoice)
            if supplier is not None and result.itc_at_risk:
                per_supplier[supplier.supplier_name] = (
                    per_supplier.get(supplier.supplier_name, Decimal("0"))
                    + result.itc_at_risk
                )
                destination = per_supplier_potential if is_potential else per_supplier_confirmed
                destination[supplier.supplier_name] = (
                    destination.get(supplier.supplier_name, Decimal("0")) + result.itc_at_risk
                )
        return cls(
            results=results,
            supplier_drafts=supplier_drafts or {},
            counts=counts,
            total_itc_at_risk=confirmed + potential,
            per_supplier_itc_at_risk=per_supplier,
            confirmed_itc_at_risk=confirmed,
            potential_itc_at_risk=potential,
            per_supplier_confirmed_itc_at_risk=per_supplier_confirmed,
            per_supplier_potential_itc_at_risk=per_supplier_potential,
        )
