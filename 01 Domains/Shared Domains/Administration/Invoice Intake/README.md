# Invoice Intake

Invoice Intake is a **Shared Domains** capability, not owned by Restaurant or
any other Business Domain. It owns **document acquisition, OCR/parsing,
normalization, review, and routing** for supplier invoices and similar
source documents — the acquisition/process layer, industry-independent by
nature (any Business Domain that receives supplier documents can reuse it).

It does **not** own the canonical business/cost model those documents feed.
Business Domains such as `01 Domains/Business Domain/Restaurant/Purchasing/`
consume the normalized document Invoice Intake produces and apply their own
domain-specific processing (classification, costing, reconciliation) to it.
This mirrors the same acquisition-vs-domain-meaning split already
established for Clover data acquisition (`Technical/Connectors` acquires,
Domains interpret) — Invoice Intake is that same split applied to supplier
document intake instead of a POS API.

## Structure

- `Invoices/Raw/` — original source documents exactly as received (PDFs,
  scanned photos), unmodified, preserved for reference and reprocessing.
- `Invoices/Reviewed/` — reserved for verified/reference datasets: documents
  whose extracted data has been human-confirmed.
- `Invoices/TestCases/` — reserved for verified/reference datasets used to
  validate acquisition/parsing behavior.

## Related

- `03 Software/InvoiceIntake/` — the current runtime prototype (upload → OCR
  → review → normalized output), Software-layer, not moved by this task.
- `01 Domains/Business Domain/Restaurant/Purchasing/` — the Business Domain
  that consumes Invoice Intake's normalized output today (`Purchase
  Document`/`Purchase Line`); see `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md`
  for the prior reconciliation of an earlier, Administration-local invoice
  model into that canonical Purchasing model.
- See also `01 Domains/Shared Domains/Purchased/README.md` — a later,
  cross-Business-Domain Shared Domain formalizing the general "purchase
  fact" concept. It does not redirect this module's existing output or
  redefine its scope; the relationship between the two is recorded there as
  an explicitly open question, not decided by either document.
