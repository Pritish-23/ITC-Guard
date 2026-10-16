from datetime import date
from decimal import Decimal
from pathlib import Path

from itcguard.agents.graph import invoke_offline
from itcguard.agents.reviewer import review_drafts, validate_grounded_text
from itcguard.ingest import ingest_invoices
from itcguard.models import Invoice, InvoiceSource, MatchResult, MatchStatus


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _fixture_state() -> dict:
    return {
        "books_invoices": ingest_invoices(
            FIXTURES / "purchase_register.csv",
            FIXTURES / "mappings" / "purchase_register.json",
            InvoiceSource.BOOKS,
        ),
        "gstr2b_invoices": ingest_invoices(
            FIXTURES / "gstr2b.csv",
            FIXTURES / "mappings" / "gstr2b.json",
            InvoiceSource.GSTR2B,
        ),
    }


def _invoice() -> Invoice:
    return Invoice(
        source=InvoiceSource.BOOKS,
        row_id="books-1",
        supplier_gstin="27AAAAA0000A1Z5",
        supplier_name="Example Supplier",
        invoice_number_raw="INV-1",
        invoice_number_norm="INV1",
        invoice_date=date(2026, 1, 2),
        taxable_value=Decimal("1000.00"),
        igst=Decimal("180.00"),
        cgst=Decimal("0"),
        sgst=Decimal("0"),
        cess=Decimal("0"),
        invoice_value=Decimal("1180.00"),
    )


def test_graph_runs_all_agent_stages_offline_and_preserves_statuses() -> None:
    state = invoke_offline(_fixture_state())

    assert len(state["match_results"]) == 42
    assert len(state["explanations"]) == 10
    assert set(state["drafts"]) == {
        "Fictional Alpha Industrial Supplies",
        "Fictional Beta Circuitry Works",
        "Fictional Fable Logistics Lab",
    }
    assert state["report"].supplier_drafts == state["drafts"]
    assert state["review"]["approved"] is True
    possible = [
        result
        for result in state["match_results"]
        if result.status is MatchStatus.POSSIBLE_MATCH
    ]
    assert len(possible) == 3
    assert all(result.human_confirmation_required for result in possible)
    assert all(result.resolver_suggestion for result in possible)


def test_guardrail_rejects_invented_amounts() -> None:
    invoice = _invoice()
    assert validate_grounded_text("Invoice INV-1 dated 2026-01-02: ₹999.00", [invoice]) == (
        False,
        "unknown amount ₹999.00",
    )

    result = MatchResult(
        status=MatchStatus.MISSING_IN_2B,
        books_invoice=invoice,
        explanation="Invoice INV-1 is missing from GSTR-2B.",
        itc_at_risk=Decimal("180.00"),
    )
    state = review_drafts(
        {
            "match_results": [result],
            "drafts": {"Example Supplier": "Invoice INV-1 dated 2026-01-02: ₹999.00"},
        }
    )
    assert "999" not in state["drafts"]["Example Supplier"]
    assert state["review"]["requires_human_confirmation"] is True


class _RetryProvider:
    def __init__(self) -> None:
        self.calls = 0

    def structured_completion(self, messages, *, output_schema=None):
        self.calls += 1
        return {
            "structured": {
                "draft": "Please review invoice INV-1 dated 2026-01-02."
            }
        }


def test_reviewer_retries_once_and_accepts_grounded_candidate() -> None:
    invoice = _invoice()
    provider = _RetryProvider()
    result = MatchResult(status=MatchStatus.MISSING_IN_2B, books_invoice=invoice)
    state = review_drafts(
        {
            "match_results": [result],
            "drafts": {"Example Supplier": "Invoice INV-999 dated 2026-01-02."},
        },
        provider,
    )

    assert provider.calls == 1
    assert state["drafts"]["Example Supplier"].startswith("Please review invoice INV-1")
    assert state["review"]["approved"] is True
