"""Serialization and file output for reconciliation results."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from .models import ReconciliationReport


def _json_value(value: Any) -> Any:
    """Convert domain values to deterministic, lossless JSON values."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def report_to_dict(report: ReconciliationReport) -> dict[str, Any]:
    """Return the complete report as JSON-compatible data."""
    return _json_value(report)


def serialize_report(report: ReconciliationReport) -> dict[str, Any]:
    """Compatibility-friendly public alias for JSON-compatible report data."""
    return report_to_dict(report)


def write_report(report: ReconciliationReport, output_dir: str | Path) -> Path:
    """Write the deterministic reconciliation report and draft placeholder."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "report.json"
    report_path.write_text(
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    drafts_path = directory / "supplier_drafts.json"
    drafts_path.write_text(
        json.dumps(_json_value(report.supplier_drafts), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path
