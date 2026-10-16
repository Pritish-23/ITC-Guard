# ITC Guard

ITC Guard helps small business owners, accountants, and bookkeepers reconcile a purchase register against a GSTR-2B export. It flags missing and mismatched invoices, quantifies input tax credit (ITC) at risk in rupees, explains each issue in plain English, and drafts supplier follow-ups.

This repository is being built for the **OmniRush Frontier Buildathon 2026**, Agents & Automation track. The project is currently at the reproducible skeleton and synthetic-fixture stage; the deterministic ingest and matching engine is the next implementation step.

## Design principles

- Money-critical matching is deterministic Python code, not an LLM decision.
- All money values use `Decimal`, never binary floating point.
- The default LLM provider will be a deterministic, offline mock.
- Any future resolver suggestion remains a human-confirmation suggestion and does not silently overwrite the deterministic match status.
- Reviewer guardrails will reject explanations or drafts containing invoice numbers, dates, GSTINs, or rupee amounts that are not present in the supplier's underlying data.

## Current repository layout

```text
src/itcguard/       Python package and CLI scaffold
tests/              Offline pytest checks
fixtures/           Synthetic CSV/JSON data and mapping examples
Dockerfile          Reproducible Python 3.12 image
Makefile            Single offline test command plus local entry points
pyproject.toml      Project metadata and pinned dependency requirements
uv.lock             Committed dependency lockfile
```

## Quick start with uv

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/). The project pins Python 3.12 in `.python-version`.

```bash
uv sync --locked --dev
make test
```

The test command uses `uv run --offline pytest`, so after dependencies have been prepared it does not contact the network.

## Docker build and offline test

The intended judge-style check is:

```bash
docker build -t itcguard .
docker run --rm --network none itcguard make test
```

The Dockerfile installs `make`, copies the lockfile and project files, and performs dependency installation during the image build. The container's default command is `make test`.

## Fixtures and mappings

The bundled data is synthetic and uses clearly fake GSTINs. It contains seeded examples for ordinary matches, invoice-number normalization, rounding tolerance, amount mismatch, missing invoices on either side, possible matches, duplicates, GSTIN typo candidates, and grouped supplier issues. See [`fixtures/SEEDED_CASES.md`](fixtures/SEEDED_CASES.md).

The mapping examples are JSON files under `fixtures/mappings/`. The canonical fixture fields are:

```text
supplier_gstin, supplier_name, invoice_number, invoice_date,
taxable_value, igst, cgst, sgst, cess, invoice_value
```

The exact GSTR-2B export layout has not been verified in this project. **Check and update the mapping against the official GSTR-2B format before using real data.** This project is not a GST portal integration.

## Planned CLI usage

The CLI MVP is available now:

```bash
itcguard reconcile \
  --books fixtures/purchase_register.csv \
  --gstr2b fixtures/gstr2b.csv \
  --mapping fixtures/mappings/purchase_register.json \
  --out reports
```

The command ingests both sources, runs the deterministic matcher and offline LangGraph agent pipeline, prints status counts and ITC-at-risk totals, and writes:

- `reports/report.json` — complete machine-readable reconciliation report
- `reports/supplier_drafts.json` — one reviewed, grouped draft per affected supplier

For the bundled synthetic fixtures, the current report contains 32 matched results, 3 amount mismatches, 1 books-only invoice, 2 GSTR-2B-only invoices, 3 possible matches, and 1 duplicate. The total ITC at risk is ₹4,206.00.

The agent pipeline is fully offline by default: resolver suggestions, explanations, and grouped drafts use the deterministic `MockProvider`; the reviewer checks grounding and safety, retries once, and falls back to a safe template when generated text is invalid.

## Optional FastAPI demo

The CLI remains the primary interface, but the same flow is available as a small local FastAPI demo:

```bash
make api
```

Open <http://localhost:8000/report> to view the bundled report. The API also exposes:

- `GET /health` — health check
- `GET /` — demo landing page
- `POST /reconcile` — JSON report using bundled fixtures by default
- `GET /report` — readable HTML report with counts, explanations, and supplier drafts

The API has no authentication, database, or network provider. It is intended for local demonstration only.

## Configuration

Copy `.env.example` to `.env` for local configuration if needed. The default provider is always the offline mock. No credentials or real provider keys belong in this repository.

## Out of scope for the MVP

- Real GST portal integration or login
- OCR for PDFs or scanned invoices
- Authentication, multi-user workflows, and a database beyond files/in-memory state
- Credit notes, debit notes, reverse charge, and other special cases
- Legal or tax advice; ITC Guard flags and explains data differences but does not advise

FastAPI reporting is intentionally deferred until the CLI flow is stable. A polished CLI is the minimum shipped interface.

## Buildathon workflow

The project is built in small, locally committed steps with OmniRush. The default branch is kept runnable after each step. Sub-agents are used for isolated work such as synthetic fixtures and later agent-layer reviews; their changes are checked by the main session before commit. No GitHub push is performed until the owner explicitly approves it.

## License

MIT. See [`LICENSE`](LICENSE).
