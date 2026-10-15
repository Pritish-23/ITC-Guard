from datetime import date
from decimal import Decimal

from itcguard.matcher import reconcile
from itcguard.models import Invoice, InvoiceSource, MatchStatus
from itcguard.settings import ReconciliationSettings


def invoice(
    source: InvoiceSource,
    row_id: str,
    number: str,
    *,
    gstin: str = "27AAAAA0000A1Z5",
    invoice_date: date = date(2026, 10, 1),
    tax: str = "180.00",
    invoice_value: str = "1180.00",
) -> Invoice:
    return Invoice(
        source=source,
        row_id=row_id,
        supplier_gstin=gstin,
        supplier_name="Example Supplier",
        invoice_number_raw=number,
        invoice_number_norm=number.replace("/", "").replace("-", "").replace(" ", "").upper(),
        invoice_date=invoice_date,
        taxable_value="1000.00",
        igst=tax,
        cgst="0",
        sgst="0",
        cess="0",
        invoice_value=invoice_value,
    )


def test_exact_fuzzy_and_possible_tiers_are_applied_in_order() -> None:
    books = [
        invoice(InvoiceSource.BOOKS, "b-exact", "INV/001"),
        invoice(InvoiceSource.BOOKS, "b-fuzzy", "INV/100"),
        invoice(InvoiceSource.BOOKS, "b-possible", "INV/003"),
        invoice(InvoiceSource.BOOKS, "b-typo", "INV/777", gstin="27AAAAA0000A1Z6"),
    ]
    gstr = [
        invoice(InvoiceSource.GSTR2B, "g-exact", "INV-001"),
        invoice(InvoiceSource.GSTR2B, "g-fuzzy", "INV/10X"),
        invoice(InvoiceSource.GSTR2B, "g-possible", "INV/999"),
        invoice(InvoiceSource.GSTR2B, "g-typo", "INV/777"),
    ]

    results = reconcile(books, gstr, ReconciliationSettings(max_edit_distance=1))

    by_book = {result.books_invoice.row_id: result for result in results if result.books_invoice}
    assert by_book["b-exact"].status is MatchStatus.MATCHED
    assert by_book["b-fuzzy"].status is MatchStatus.MATCHED
    assert by_book["b-possible"].status is MatchStatus.POSSIBLE_MATCH
    assert by_book["b-typo"].status is MatchStatus.POSSIBLE_MATCH
    assert by_book["b-possible"].human_confirmation_required
    assert by_book["b-typo"].human_confirmation_required


def test_tolerance_controls_match_and_date_candidate() -> None:
    books = [invoice(InvoiceSource.BOOKS, "b1", "INV/001", tax="180.50")]
    gstr = [invoice(InvoiceSource.GSTR2B, "g1", "INV/001", tax="180.00")]

    assert (
        reconcile(books, gstr, ReconciliationSettings(amount_tolerance="0.25"))[0].status
        is MatchStatus.AMOUNT_MISMATCH
    )
    result = reconcile(books, gstr, ReconciliationSettings(amount_tolerance="0.50"))[0]
    assert result.status is MatchStatus.MATCHED
    assert result.notes == ["Matched within configured amount tolerance."]

    date_books = [invoice(InvoiceSource.BOOKS, "b2", "INV/002")]
    date_gstr = [
        invoice(
            InvoiceSource.GSTR2B,
            "g2",
            "INV/999",
            invoice_date=date(2026, 10, 2),
        )
    ]
    assert reconcile(date_books, date_gstr)[0].status is MatchStatus.MISSING_IN_2B
    assert (
        reconcile(
            date_books,
            date_gstr,
            ReconciliationSettings(date_tolerance_days=1),
        )[0].status
        is MatchStatus.POSSIBLE_MATCH
    )


def test_duplicate_rows_do_not_consume_the_canonical_counterpart() -> None:
    books = [
        invoice(InvoiceSource.BOOKS, "b2", "INV/001"),
        invoice(InvoiceSource.BOOKS, "b1", "INV/001"),
    ]
    gstr = [invoice(InvoiceSource.GSTR2B, "g1", "INV/001")]

    results = reconcile(books, gstr)

    assert [result.status for result in results] == [MatchStatus.MATCHED, MatchStatus.DUPLICATE]
    assert results[0].books_invoice.row_id == "b1"
    assert results[0].gstr2b_invoice.row_id == "g1"


def test_risk_uses_decimal_books_tax_and_positive_mismatch_only() -> None:
    missing = reconcile(
        [invoice(InvoiceSource.BOOKS, "b1", "INV/001", tax="180.00")],
        [],
    )[0]
    assert missing.status is MatchStatus.MISSING_IN_2B
    assert missing.itc_at_risk == Decimal("180.00")

    mismatch = reconcile(
        [invoice(InvoiceSource.BOOKS, "b2", "INV/002", tax="200.00")],
        [invoice(InvoiceSource.GSTR2B, "g2", "INV/002", tax="180.00")],
    )[0]
    assert mismatch.status is MatchStatus.AMOUNT_MISMATCH
    assert mismatch.tax_difference == Decimal("20.00")
    assert mismatch.itc_at_risk == Decimal("20.00")

    lower_books = reconcile(
        [invoice(InvoiceSource.BOOKS, "b3", "INV/003", tax="170.00")],
        [invoice(InvoiceSource.GSTR2B, "g3", "INV/003", tax="180.00")],
    )[0]
    assert lower_books.itc_at_risk == Decimal("0")


def test_results_are_reproducible_when_input_rows_are_reordered() -> None:
    books = [
        invoice(InvoiceSource.BOOKS, "b2", "INV/002"),
        invoice(InvoiceSource.BOOKS, "b1", "INV/001"),
    ]
    gstr = [
        invoice(InvoiceSource.GSTR2B, "g2", "INV/002"),
        invoice(InvoiceSource.GSTR2B, "g1", "INV/001"),
    ]

    first = reconcile(books, gstr)
    second = reconcile(list(reversed(books)), list(reversed(gstr)))

    def shape(results: list) -> list[tuple[MatchStatus, str | None, str | None]]:
        return [
            (
                result.status,
                result.books_invoice and result.books_invoice.row_id,
                result.gstr2b_invoice and result.gstr2b_invoice.row_id,
            )
            for result in results
        ]

    assert shape(first) == shape(second)
