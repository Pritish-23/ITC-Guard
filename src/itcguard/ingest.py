"""CSV/JSON invoice ingestion with contextual validation errors."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .models import Invoice, InvoiceSource
from .normalize import (
    normalize_gstin,
    normalize_invoice_number,
    parse_decimal_amount,
    parse_invoice_date,
)

CANONICAL_FIELDS: tuple[str, ...] = (
    "supplier_gstin",
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "taxable_value",
    "igst",
    "cgst",
    "sgst",
    "cess",
    "invoice_value",
)
MONEY_FIELDS = frozenset(CANONICAL_FIELDS[4:])


class IngestionError(ValueError):
    """A source, mapping, or row validation error during ingestion."""


def _source_label(source: InvoiceSource | str) -> str:
    if isinstance(source, InvoiceSource):
        return source.value
    return str(source)


def _context(
    source: str,
    row: int | None = None,
    column: str | None = None,
) -> str:
    parts = [f"source={source!r}"]
    if row is not None:
        parts.append(f"row={row}")
    if column is not None:
        parts.append(f"column={column!r}")
    return ", ".join(parts)


def _source_path(path: str | Path, source: str | None = None) -> str:
    return f"{source} ({path})" if source else str(path)


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Load a CSV or JSON record list from *path*."""

    file_path = Path(path)
    if not file_path.is_file():
        raise IngestionError(f"source file not found: {file_path}")
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".csv":
            with file_path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            if not rows and not _csv_has_header(file_path):
                raise IngestionError(f"source={str(file_path)!r}: CSV has no header")
            return [dict(row) for row in rows]
        if suffix == ".json":
            with file_path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            raise IngestionError(
                f"source={str(file_path)!r}: unsupported file type {suffix or '<none>'!r}; expected CSV or JSON"
            )
    except IngestionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise IngestionError(f"source={str(file_path)!r}: could not read records: {exc}") from exc

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        payload = payload["records"]
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise IngestionError(
            f"source={str(file_path)!r}: JSON must contain a list of object records"
        )
    return [dict(row) for row in payload]


def _csv_has_header(path: Path) -> bool:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return bool(handle.readline().strip())


def load_mapping(path: str | Path) -> dict[str, str]:
    """Load and validate a canonical-field to source-column mapping."""

    mapping_path = Path(path)
    if not mapping_path.is_file():
        raise IngestionError(f"mapping file not found: {mapping_path}")
    try:
        with mapping_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IngestionError(
            f"mapping source={str(mapping_path)!r}: could not read mapping: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise IngestionError(
            f"mapping source={str(mapping_path)!r}: mapping must be a JSON object"
        )
    candidate = payload.get("column_mapping", payload)
    if not isinstance(candidate, dict):
        raise IngestionError(
            f"mapping source={str(mapping_path)!r}: column_mapping must be an object"
        )
    missing = [field for field in CANONICAL_FIELDS if field not in candidate]
    if missing:
        raise IngestionError(
            f"mapping source={str(mapping_path)!r}: missing canonical field(s): {', '.join(missing)}"
        )
    invalid = [
        field
        for field in CANONICAL_FIELDS
        if not isinstance(candidate[field], str) or not candidate[field].strip()
    ]
    if invalid:
        raise IngestionError(
            f"mapping source={str(mapping_path)!r}: field(s) have empty/non-string source columns: {', '.join(invalid)}"
        )
    return {field: candidate[field].strip() for field in CANONICAL_FIELDS}


def _as_source(source: InvoiceSource | str) -> InvoiceSource:
    if isinstance(source, InvoiceSource):
        return source
    try:
        return InvoiceSource(str(source).strip().lower())
    except ValueError as exc:
        raise IngestionError(
            f"source={source!r}: source must be one of {', '.join(item.value for item in InvoiceSource)}"
        ) from exc


def _check_columns(
    rows: Sequence[Mapping[str, Any]],
    mapping: Mapping[str, str],
    *,
    source: str,
) -> None:
    if not rows:
        return
    available = set(rows[0])
    for field in CANONICAL_FIELDS:
        column = mapping[field]
        if column not in available:
            raise IngestionError(
                f"{_context(source, column=column)}: mapping for canonical field {field!r} references a missing source column"
            )


def _required_value(
    row: Mapping[str, Any],
    field: str,
    column: str,
    *,
    source: str,
    row_number: int,
) -> Any:
    if column not in row or row[column] is None or str(row[column]).strip() == "":
        raise IngestionError(
            f"{_context(source, row_number, column)}: missing required field {field!r}"
        )
    return row[column]


def normalize_invoice_row(
    row: Mapping[str, Any],
    mapping: Mapping[str, str],
    source: InvoiceSource | str,
    row_number: int,
    *,
    financial_year_prefix: str | None = None,
    financial_year_suffix: str | None = None,
    source_name: str | None = None,
) -> Invoice:
    """Validate and convert one source row into a typed :class:`Invoice`."""

    invoice_source = _as_source(source)
    source_label = source_name or _source_label(invoice_source)
    values = {
        field: _required_value(
            row,
            field,
            mapping[field],
            source=source_label,
            row_number=row_number,
        )
        for field in CANONICAL_FIELDS
    }
    warnings_list: list[str] = []
    gstin = normalize_gstin(
        values["supplier_gstin"],
        warning_context=_context(source_label, row_number, mapping["supplier_gstin"]),
        warnings_list=warnings_list,
    )
    raw_number = str(values["invoice_number"])
    try:
        invoice_date = parse_invoice_date(values["invoice_date"])
    except ValueError as exc:
        raise IngestionError(
            f"{_context(source_label, row_number, mapping['invoice_date'])}: {exc}"
        ) from exc
    amounts: dict[str, Any] = {}
    for field in CANONICAL_FIELDS[4:]:
        try:
            amounts[field] = parse_decimal_amount(values[field])
        except ValueError as exc:
            raise IngestionError(
                f"{_context(source_label, row_number, mapping[field])}: {exc}"
            ) from exc

    normalized_number = normalize_invoice_number(
        raw_number,
        financial_year_prefix=financial_year_prefix,
        financial_year_suffix=financial_year_suffix,
    )
    if not normalized_number:
        raise IngestionError(
            f"{_context(source_label, row_number, mapping['invoice_number'])}: invoice number normalizes to empty"
        )
    return Invoice(
        source=invoice_source,
        row_id=f"{invoice_source.value}-{row_number}",
        supplier_gstin=gstin,
        supplier_name=str(values["supplier_name"]).strip(),
        invoice_number_raw=raw_number,
        invoice_number_norm=normalized_number,
        invoice_date=invoice_date,
        taxable_value=amounts["taxable_value"],
        igst=amounts["igst"],
        cgst=amounts["cgst"],
        sgst=amounts["sgst"],
        cess=amounts["cess"],
        invoice_value=amounts["invoice_value"],
    )



def ingest_invoices(
    data_path: str | Path,
    mapping_path: str | Path,
    source: InvoiceSource | str,
    *,
    financial_year_prefix: str | None = None,
    financial_year_suffix: str | None = None,
) -> list[Invoice]:
    """Load, validate, normalize, and type all invoice records in a file."""

    invoice_source = _as_source(source)
    records = load_records(data_path)
    mapping = load_mapping(mapping_path)
    source_label = _source_path(data_path, invoice_source.value)
    _check_columns(records, mapping, source=source_label)
    return [
        normalize_invoice_row(
            row,
            mapping,
            invoice_source,
            row_number=index + 2
            if Path(data_path).suffix.lower() == ".csv"
            else index + 1,
            financial_year_prefix=financial_year_prefix,
            financial_year_suffix=financial_year_suffix,
            source_name=source_label,
        )
        for index, row in enumerate(records)
    ]


# Explicit aliases keep the module convenient for CLI and library callers.
load_invoices = ingest_invoices
read_records = load_records
read_mapping = load_mapping
