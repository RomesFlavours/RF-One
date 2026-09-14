# Invoice Intake

Invoice Intake is a **Cross Domain** capability, not owned by Restaurant or
any other Business Domain. It owns **document acquisition, OCR/parsing,
normalization, review, and routing** for supplier invoices and similar
source documents — the acquisition/process layer, industry-independent by
nature (any Business Domain that receives supplier documents can reuse it).

It does **not** own the canonical business/cost model those documents feed.
This mirrors the same acquisition-vs-domain-meaning split already
established for Clover data acquisition (`Technical/Connectors` acquires,
Domains interpret) — Invoice Intake is that same split applied to supplier
document intake instead of a POS API.

**Ownership (Align legacy Invoice Intake with Purchased):** the canonical
Purchase Fact that Invoice Intake's normalized output feeds is owned by
**Purchased** (`01 Domains/Cross Domain/Purchased/README.md`), a Shared
Domain — capture + normalize + publish. Business Domains such as
`01 Domains/Business Domain/Restaurant/Purchasing/` are *consumers* of that
Purchase Fact for their own domain-specific processing (Purchase Order,
Configured Expectation, Physical Receiving, Reconciliation, Alert) — they no
longer own it, and owning it is never a prerequisite for Invoice Intake to
produce one. See Purchased's README, "Relationship to Restaurant's existing
Purchasing module — Invoice Intake alignment (closed)."

## Structure

- `Invoices/Raw/` — original source documents exactly as received (PDFs,
  scanned photos), unmodified, preserved for reference and reprocessing.
- `Invoices/Reviewed/` — reserved for verified/reference datasets: documents
  whose extracted data has been human-confirmed.
- `Invoices/TestCases/` — reserved for verified/reference datasets used to
  validate acquisition/parsing behavior.

## Related

- `03 Software/InvoiceIntake/` — the current runtime prototype (upload → OCR
  → review → normalized output), Software-layer. Its `purchased_bridge.py`
  (renamed from `purchasing_bridge.py` by "Align legacy Invoice Intake with
  Purchased") persists that output as Purchased's canonical Purchase Fact.
- `01 Domains/Cross Domain/Purchased/README.md` — the Shared Domain that
  now canonically owns the Purchase Fact this module's output feeds (capture
  + normalize + publish); see its "Invoice Intake alignment (closed)" note.
- `01 Domains/Business Domain/Restaurant/Purchasing/` — the Business Domain
  that *consumes* Invoice Intake's normalized output (`Purchase
  Document`/`Purchase Line`) for its own remaining scope (Purchase Order,
  Configured Expectation, Physical Receiving, Reconciliation, Alert) — it no
  longer owns the Purchase Fact itself; see
  `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md` for the prior
  reconciliation of an earlier, Administration-local invoice model into that
  Purchasing model.
