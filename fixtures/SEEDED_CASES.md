# Synthetic seeded reconciliation cases

These fixtures are deterministic, synthetic data for development and testing. All six supplier names are fictional, and every GSTIN is a clearly fake 15-character value. The CSV and JSON numeric fields are decimal strings and dates use `DD-MM-YYYY`.

The canonical schema in both datasets is:

`supplier_gstin,supplier_name,invoice_number,invoice_date,taxable_value,igst,cgst,sgst,cess,invoice_value`

The GSTR-2B rows and mapping metadata are illustrative only. Mappings require verification against official GSTR-2B exports before any production use.

## Seeded cases

| Case | Relevant invoice IDs | Expected status | Expected ITC amount where applicable |
| --- | --- | --- | ---: |
| 1. Ordinary matched | `ALPHA-001` in books and 2B | `matched` | ₹1,800.00 |
| 2. Formatting normalization | Books `ALPHA-002`; 2B `ALPHA/002` (supplier name is also case-varied) | `matched_after_normalization` | ₹1,350.00 |
| 3. ₹1 rounding | `ALPHA-003` | `matched_with_rounding_difference`; 2B CGST is ₹1.00 lower | Books ₹900.00; 2B ₹899.00 |
| 4. Larger amount mismatch | `ALPHA-004` | `amount_mismatch` | Books ₹2,160.00; 2B ₹1,980.00 |
| 5. Books-only missing in 2B | `ALPHA-005` | `books_only` | ₹576.00 |
| 6. 2B-only missing in books | `ALPHA-008` | `two_b_only` | ₹738.00 |
| 7. Amount/date possible match | Books `ALPHA-006`; 2B `ALPHA-ALT-006` (same date and amount, deliberately non-fuzzy invoice number) | `possible_match` pending review | ₹1,530.00 |
| 8. Duplicate books row | `BETA-001` appears twice in books and once in 2B | `duplicate_books_row` | ₹1,080.00 once; duplicate book row is not additional ITC |
| 9. One-character GSTIN typo candidate | `ALPHA-007`; books GSTIN ends `Z5`, 2B GSTIN ends `Z6` | `possible_match_gstin_typo` pending verification | ₹720.00 |
| 10. One supplier with several issues | `FABLE-001` through `FABLE-007` | `supplier_issue_cluster`: amount mismatch (`FABLE-001`, `FABLE-006`), duplicate books row (`FABLE-004`), date/amount possible match (`FABLE-005` vs `FABLE-ALT-005`), books-only (`FABLE-002`), and 2B-only (`FABLE-007`) | `FABLE-001`: books ₹900.00 / 2B ₹850.00; `FABLE-002`: ₹648.00; `FABLE-003`: ₹1,116.00; `FABLE-004`: ₹792.00 once; `FABLE-005`: ₹1,044.00; `FABLE-006`: books ₹1,206.00 / 2B ₹1,100.00; `FABLE-007`: ₹450.00 |

The remaining Beta, Cobalt, Delta, and Ember rows are deterministic ordinary matched controls, except for the explicitly described Beta duplicate and Fable issue cluster.
