from collections import Counter
from decimal import Decimal
from pathlib import Path

from itcguard.ingest import ingest_invoices
from itcguard.matcher import reconcile
from itcguard.models import InvoiceSource, MatchStatus


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _fixture_results():
    books = ingest_invoices(
        FIXTURES / "purchase_register.csv",
        FIXTURES / "mappings" / "purchase_register.json",
        InvoiceSource.BOOKS,
    )
    gstr2b = ingest_invoices(
        FIXTURES / "gstr2b.csv",
        FIXTURES / "mappings" / "gstr2b.json",
        InvoiceSource.GSTR2B,
    )
    return reconcile(books, gstr2b)


def test_default_fixture_covers_every_required_status() -> None:
    results = _fixture_results()
    counts = Counter(result.status for result in results)

    assert counts == {
        MatchStatus.MATCHED: 32,
        MatchStatus.AMOUNT_MISMATCH: 3,
        MatchStatus.MISSING_IN_2B: 1,
        MatchStatus.MISSING_IN_BOOKS: 2,
        MatchStatus.POSSIBLE_MATCH: 3,
        MatchStatus.DUPLICATE: 1,
    }


def test_seeded_cases_have_expected_status_and_itc_risk() -> None:
    results = _fixture_results()
    by_books_number = {
        result.books_invoice.invoice_number_raw: result
        for result in results
        if result.books_invoice is not None
    }

    assert by_books_number["ALPHA-002"].status is MatchStatus.MATCHED
    assert by_books_number["ALPHA-003"].status is MatchStatus.MATCHED
    assert by_books_number["ALPHA-003"].notes
    assert by_books_number["ALPHA-004"].status is MatchStatus.AMOUNT_MISMATCH
    assert by_books_number["ALPHA-004"].itc_at_risk == Decimal("180.00")
    assert by_books_number["ALPHA-005"].status is MatchStatus.MISSING_IN_2B
    assert by_books_number["ALPHA-005"].itc_at_risk == Decimal("576.00")
    assert by_books_number["ALPHA-006"].status is MatchStatus.POSSIBLE_MATCH
    assert by_books_number["ALPHA-006"].itc_at_risk == Decimal("1530.00")
    assert by_books_number["ALPHA-007"].status is MatchStatus.POSSIBLE_MATCH
    assert any(
        result.status is MatchStatus.MATCHED
        and result.books_invoice is not None
        and result.books_invoice.invoice_number_raw == "BETA-001"
        for result in results
    )

    duplicate = next(result for result in results if result.status is MatchStatus.DUPLICATE)
    assert duplicate.books_invoice is not None
    assert duplicate.books_invoice.invoice_number_raw == "BETA-001"

    missing_from_books = [
        result
        for result in results
        if result.status is MatchStatus.MISSING_IN_BOOKS
    ]
    assert {result.gstr2b_invoice.invoice_number_raw for result in missing_from_books} == {
        "ALPHA-008",
        "FABLE-007",
    }


def test_default_fixture_reconciliation_is_reproducible() -> None:
    books = ingest_invoices(
        FIXTURES / "purchase_register.csv",
        FIXTURES / "mappings" / "purchase_register.json",
        InvoiceSource.BOOKS,
    )
    gstr2b = ingest_invoices(
        FIXTURES / "gstr2b.csv",
        FIXTURES / "mappings" / "gstr2b.json",
        InvoiceSource.GSTR2B,
    )
    first = reconcile(books, gstr2b)
    second = reconcile(list(reversed(books)), list(reversed(gstr2b)))

    def shape(results):
        return [
            (
                result.status,
                result.books_invoice and result.books_invoice.row_id,
                result.gstr2b_invoice and result.gstr2b_invoice.row_id,
            )
            for result in results
        ]

    assert shape(first) == shape(second)
