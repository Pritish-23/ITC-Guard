"""Small, deterministic normalizers used while ingesting invoice exports."""

from __future__ import annotations

import re
import warnings
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class InvoiceNormalizationWarning(UserWarning):
    """A non-fatal issue found while normalizing an invoice field."""


def normalize_gstin(
    value: Any,
    *,
    warning_context: str = "GSTIN",
    warnings_list: list[str] | None = None,
) -> str:
    """Trim and uppercase a GSTIN, warning when its length is not 15.

    GSTIN validation is deliberately limited to the length check here.  A
    malformed GSTIN should remain visible to the reconciliation workflow.
    """

    normalized = str(value).strip().upper()
    if len(normalized) != 15:
        message = f"{warning_context}: GSTIN has invalid length {len(normalized)} (expected 15)"
        if warnings_list is not None:
            warnings_list.append(message)
        warnings.warn(message, InvoiceNormalizationWarning, stacklevel=2)
    return normalized


def gstin_length_is_valid(value: str) -> bool:
    """Return whether a normalized GSTIN has the expected length."""

    return len(value.strip()) == 15


def _normalize_financial_year_token(value: str) -> str:
    return re.sub(r"[/_\-.\s]+", "", str(value).strip().upper())


def normalize_invoice_number(
    value: Any,
    *,
    financial_year_prefix: str | None = None,
    financial_year_suffix: str | None = None,
) -> str:
    """Return a stable invoice number suitable for deterministic matching.

    Separators commonly introduced by exports are removed and every numeric
    run has leading zeroes stripped.  Optional financial-year tokens can be
    removed from either edge after the same normalization is applied.
    """

    raw = str(value).strip().upper()
    if not raw:
        return ""
    normalized = re.sub(
        r"\d+",
        lambda match: str(int(match.group(0))),
        raw,
    )
    normalized = re.sub(r"[/\-_\s.]+", "", normalized)

    if financial_year_prefix:
        prefix = _normalize_financial_year_token(financial_year_prefix)
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    if financial_year_suffix:
        suffix = _normalize_financial_year_token(financial_year_suffix)
        if suffix and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized


def parse_invoice_date(value: Any) -> date:
    """Parse the three supported invoice date formats.

    Slash dates with both day and month at most 12 are rejected because they
    cannot be distinguished from the common MM/DD interpretation.  Hyphen
    dates are explicitly DD-MM-YYYY and ISO dates are unambiguous.
    """

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("invoice date is empty")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid ISO invoice date {text!r}") from exc

    match = re.fullmatch(r"(\d{2})([-/])(\d{2})[-/](\d{4})", text)
    if not match or match.group(2) != text[2:3] or text[5] != match.group(2):
        raise ValueError(f"invalid invoice date format {text!r}")
    day, separator, month, year = match.groups()
    if separator == "/" and int(day) <= 12 and int(month) <= 12:
        raise ValueError(f"ambiguous invoice date {text!r}")
    try:
        return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise ValueError(f"invalid invoice date {text!r}") from exc


def parse_decimal_amount(value: Any) -> Decimal:
    """Parse a rupee amount without using binary floating point."""

    if isinstance(value, bool):
        raise ValueError("amount must be a decimal-compatible value")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace("₹", "").replace("\u00a0", "")
    text = re.sub(r"\s+", "", text)
    if not text:
        raise ValueError("amount is empty")

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if text.startswith(("+", "-")):
        sign = text[0]
        text = text[1:]
    else:
        sign = ""
    if not re.fullmatch(r"\d[\d,]*(?:\.\d+)?", text):
        raise ValueError(f"malformed decimal amount {value!r}")
    integer, dot, fraction = text.partition(".")
    if "," in integer:
        groups = integer.split(",")
        if not 1 <= len(groups[0]) <= 3 or any(
            len(group) not in (2, 3) for group in groups[1:]
        ):
            raise ValueError(f"malformed decimal amount {value!r}")
    digits = integer.replace(",", "") + (dot + fraction if dot else "")
    signed = ("-" if negative else sign) + digits
    try:
        return Decimal(signed)
    except InvalidOperation as exc:
        raise ValueError(f"malformed decimal amount {value!r}") from exc


# Friendly aliases for callers that prefer verb-based names.
normalize_amount = parse_decimal_amount
parse_date = parse_invoice_date
