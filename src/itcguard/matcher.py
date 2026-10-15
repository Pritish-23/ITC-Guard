"""Deterministic invoice matching for the purchase register and GSTR-2B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Iterable

from .models import Invoice, MatchResult, MatchStatus, MatchTier
from .settings import ReconciliationSettings


@dataclass(frozen=True, slots=True)
class _Pair:
    """A selected pair of sorted source indexes and the tier that selected it."""

    gstr_index: int
    tier: MatchTier
    possible_kind: str | None = None


def _normalized(value: str) -> str:
    """Compare already-normalized fields defensively across casing/whitespace."""

    return value.strip().upper()


def _invoice_key(invoice: Invoice) -> tuple[str, str]:
    return (_normalized(invoice.supplier_gstin), _normalized(invoice.invoice_number_norm))


def _record_key(invoice: Invoice) -> tuple[str, str, str, str, date]:
    """Stable ordering independent of the order in which a caller supplied rows."""

    return (
        invoice.row_id,
        _normalized(invoice.supplier_gstin),
        _normalized(invoice.invoice_number_norm),
        invoice.invoice_number_raw,
        invoice.invoice_date,
    )


def _edit_distance(left: str, right: str) -> int:
    """Return Levenshtein distance using only standard-library operations."""

    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_position, left_char in enumerate(left, start=1):
        current = [left_position]
        for right_position, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_position] + 1,
                    previous[right_position - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _amount_differences(books: Invoice, gstr2b: Invoice) -> list[tuple[str, Decimal]]:
    """Return the configured amount fields that differ, preserving Decimal math."""

    differences = [
        ("igst", abs(books.igst - gstr2b.igst)),
        ("cgst", abs(books.cgst - gstr2b.cgst)),
        ("sgst", abs(books.sgst - gstr2b.sgst)),
        ("cess", abs(books.cess - gstr2b.cess)),
        ("total_tax", abs(books.total_tax - gstr2b.total_tax)),
        ("invoice_value", abs(books.invoice_value - gstr2b.invoice_value)),
    ]
    return differences


def _amounts_within_tolerance(
    books: Invoice,
    gstr2b: Invoice,
    tolerance: Decimal,
) -> bool:
    return all(difference <= tolerance for _, difference in _amount_differences(books, gstr2b))


def _dates_within_tolerance(
    books: Invoice,
    gstr2b: Invoice,
    date_tolerance_days: int,
) -> bool:
    return abs((books.invoice_date - gstr2b.invoice_date).days) <= date_tolerance_days


def _duplicate_indexes(invoices: list[Invoice]) -> set[int]:
    """Keep the stable first row as canonical and mark subsequent rows duplicate."""

    groups: dict[tuple[str, str], list[int]] = {}
    for index, invoice in enumerate(invoices):
        groups.setdefault(_invoice_key(invoice), []).append(index)

    duplicates: set[int] = set()
    for indexes in groups.values():
        duplicates.update(indexes[1:])
    return duplicates


def _tax_difference(books: Invoice, gstr2b: Invoice) -> Decimal:
    return books.total_tax - gstr2b.total_tax


def _pair_result(
    books: Invoice,
    gstr2b: Invoice,
    *,
    tier: MatchTier,
    possible_kind: str | None = None,
    tolerance: Decimal,
) -> MatchResult:
    differences = _amount_differences(books, gstr2b)
    within_tolerance = all(difference <= tolerance for _, difference in differences)

    if possible_kind is not None:
        status = MatchStatus.POSSIBLE_MATCH
        notes = [possible_kind]
        return MatchResult(
            status=status,
            books_invoice=books,
            gstr2b_invoice=gstr2b,
            match_tier=tier,
            tax_difference=_tax_difference(books, gstr2b),
            itc_at_risk=books.total_tax,
            notes=notes,
            explanation="Possible match requires human confirmation.",
            human_confirmation_required=True,
            resolver_suggestion="Review the invoice identity and accept or reject this candidate.",
        )

    tax_difference = _tax_difference(books, gstr2b)
    if within_tolerance:
        notes = []
        if any(difference for _, difference in differences):
            notes.append("Matched within configured amount tolerance.")
        return MatchResult(
            status=MatchStatus.MATCHED,
            books_invoice=books,
            gstr2b_invoice=gstr2b,
            match_tier=tier,
            tax_difference=tax_difference,
            itc_at_risk=Decimal("0"),
            notes=notes,
            explanation="The books invoice matches a GSTR-2B invoice.",
        )

    return MatchResult(
        status=MatchStatus.AMOUNT_MISMATCH,
        books_invoice=books,
        gstr2b_invoice=gstr2b,
        match_tier=tier,
        tax_difference=tax_difference,
        itc_at_risk=max(tax_difference, Decimal("0")),
        notes=["Tax or invoice amounts exceed the configured tolerance."],
        explanation="The invoice identity matched, but the reported amounts differ.",
    )


def _missing_books_result(invoice: Invoice) -> MatchResult:
    return MatchResult(
        status=MatchStatus.MISSING_IN_BOOKS,
        gstr2b_invoice=invoice,
        itc_at_risk=Decimal("0"),
        notes=["Invoice appears in GSTR-2B but not in the purchase register."],
        explanation="This invoice is present in GSTR-2B and missing from the books.",
    )


def _missing_2b_result(invoice: Invoice) -> MatchResult:
    return MatchResult(
        status=MatchStatus.MISSING_IN_2B,
        books_invoice=invoice,
        itc_at_risk=invoice.total_tax,
        notes=["Invoice appears in the purchase register but not in GSTR-2B."],
        explanation="This invoice is present in the books and missing from GSTR-2B.",
    )


def _duplicate_result(invoice: Invoice) -> MatchResult:
    return MatchResult(
        status=MatchStatus.DUPLICATE,
        books_invoice=invoice if invoice.source.value == "books" else None,
        gstr2b_invoice=invoice if invoice.source.value == "gstr2b" else None,
        notes=["A later row has the same normalized GSTIN and invoice number in its source."],
        explanation="This invoice is a duplicate within its source and was not used for matching.",
    )


def reconcile(
    books: Iterable[Invoice],
    gstr2b: Iterable[Invoice],
    settings: ReconciliationSettings | None = None,
) -> list[MatchResult]:
    """Reconcile invoices through deterministic exact, fuzzy, and candidate tiers.

    One canonical row is retained for each source-local invoice key. Subsequent
    rows with that key become ``DUPLICATE`` results and never consume a row from
    the other source. Every remaining canonical row can participate in at most
    one pair, and output is stable by row id/source ordering.
    """

    config = settings or ReconciliationSettings()
    book_rows = sorted(list(books), key=_record_key)
    gstr_rows = sorted(list(gstr2b), key=_record_key)
    duplicate_books = _duplicate_indexes(book_rows)
    duplicate_gstr = _duplicate_indexes(gstr_rows)

    book_pairs: dict[int, _Pair] = {}
    used_gstr: set[int] = set()

    def available_book(index: int) -> bool:
        return index not in duplicate_books and index not in book_pairs

    def available_gstr(index: int) -> bool:
        return index not in duplicate_gstr and index not in used_gstr

    def assign(
        predicate: Callable[[int, int], bool],
        candidate_key: Callable[[int, int], tuple[object, ...]],
        tier: MatchTier,
        possible_kind: str | None = None,
    ) -> None:
        for book_index, book_invoice in enumerate(book_rows):
            if not available_book(book_index):
                continue
            candidates = [
                gstr_index
                for gstr_index, gstr_invoice in enumerate(gstr_rows)
                if available_gstr(gstr_index) and predicate(book_index, gstr_index)
            ]
            if not candidates:
                continue
            gstr_index = min(candidates, key=lambda index: candidate_key(book_index, index))
            book_pairs[book_index] = _Pair(gstr_index, tier, possible_kind)
            used_gstr.add(gstr_index)

    # Tier 1: exact normalized GSTIN and invoice number. Exact identity still
    # produces AMOUNT_MISMATCH when values exceed tolerance.
    assign(
        lambda bi, gi: _invoice_key(book_rows[bi]) == _invoice_key(gstr_rows[gi]),
        lambda bi, gi: (_record_key(gstr_rows[gi]),),
        MatchTier.EXACT,
    )

    # Tier 2: same GSTIN, close invoice number, and all compared amounts close.
    def fuzzy_predicate(bi: int, gi: int) -> bool:
        book = book_rows[bi]
        gstr = gstr_rows[gi]
        distance = _edit_distance(
            _normalized(book.invoice_number_norm), _normalized(gstr.invoice_number_norm)
        )
        return (
            _normalized(book.supplier_gstin) == _normalized(gstr.supplier_gstin)
            and 0 < distance <= config.max_edit_distance
            and _amounts_within_tolerance(book, gstr, config.amount_tolerance)
        )

    assign(
        fuzzy_predicate,
        lambda bi, gi: (
            _edit_distance(
                _normalized(book_rows[bi].invoice_number_norm),
                _normalized(gstr_rows[gi].invoice_number_norm),
            ),
            _record_key(gstr_rows[gi]),
        ),
        MatchTier.FUZZY,
    )

    # Tier 3: same supplier/date and amounts, but a different invoice number.
    def amount_date_predicate(bi: int, gi: int) -> bool:
        book = book_rows[bi]
        gstr = gstr_rows[gi]
        return (
            _normalized(book.supplier_gstin) == _normalized(gstr.supplier_gstin)
            and _normalized(book.invoice_number_norm)
            != _normalized(gstr.invoice_number_norm)
            and _dates_within_tolerance(book, gstr, config.date_tolerance_days)
            and _amounts_within_tolerance(book, gstr, config.amount_tolerance)
        )

    assign(
        amount_date_predicate,
        lambda bi, gi: (_record_key(gstr_rows[gi]),),
        MatchTier.AMOUNT_DATE,
        "Same GSTIN, date, and amounts with a different invoice number.",
    )

    # Tier 4: same invoice number/date/amounts, with a one- or two-character
    # GSTIN typo. This remains a possible match and is never auto-accepted.
    def gstin_typo_predicate(bi: int, gi: int) -> bool:
        book = book_rows[bi]
        gstr = gstr_rows[gi]
        distance = _edit_distance(
            _normalized(book.supplier_gstin), _normalized(gstr.supplier_gstin)
        )
        return (
            _normalized(book.invoice_number_norm) == _normalized(gstr.invoice_number_norm)
            and _dates_within_tolerance(book, gstr, config.date_tolerance_days)
            and _amounts_within_tolerance(book, gstr, config.amount_tolerance)
            and 1 <= distance <= 2
        )

    assign(
        gstin_typo_predicate,
        lambda bi, gi: (
            _edit_distance(
                _normalized(book_rows[bi].supplier_gstin),
                _normalized(gstr_rows[gi].supplier_gstin),
            ),
            _record_key(gstr_rows[gi]),
        ),
        MatchTier.AMOUNT_DATE,
        "Same invoice, date, and amounts with a possible GSTIN typo.",
    )

    results: list[MatchResult] = []
    for book_index, invoice in enumerate(book_rows):
        if book_index in duplicate_books:
            results.append(_duplicate_result(invoice))
            continue
        pair = book_pairs.get(book_index)
        if pair is None:
            results.append(_missing_2b_result(invoice))
            continue
        results.append(
            _pair_result(
                invoice,
                gstr_rows[pair.gstr_index],
                tier=pair.tier,
                possible_kind=pair.possible_kind,
                tolerance=config.amount_tolerance,
            )
        )

    for gstr_index, invoice in enumerate(gstr_rows):
        if gstr_index in duplicate_gstr:
            results.append(_duplicate_result(invoice))
        elif gstr_index not in used_gstr:
            results.append(_missing_books_result(invoice))

    return results


__all__ = ["reconcile"]
