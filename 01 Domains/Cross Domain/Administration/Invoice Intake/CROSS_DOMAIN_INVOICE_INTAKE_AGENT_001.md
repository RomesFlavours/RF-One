# Cross Domain Invoice Intake Agent — Specification V1

**Version:** 1.0 (V1 specification)
**Status:** Documentation/design only — no runtime code, schema, migration, Purchasing, or other Domain was created or modified by this task.
**Module:** Cross Domain / Administration / Invoice Intake
**Origin:** CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001

---

## 1. Purpose

Invoice Intake receives and interprets invoices/documents **on behalf of the Domain that invokes it**. It is an acquisition/interpretation capability, not a business-meaning capability.

Invoice Intake does **not** own:
- Purchasing,
- accounting,
- supplier economics,
- cost interpretation,
- or any business consequence that follows from an invoice's content.

It produces one thing — a complete, provider-agnostic, normalized representation of what a source document/payload actually says — and hands that to whichever Domain invoked it. What that Domain does with the result (classify it, cost it, reconcile it, post it) is entirely that Domain's own responsibility, never Invoice Intake's. This is the same acquisition-vs-meaning boundary already established for the Clover Technical Connector (`Technical/Connectors` acquires; Domains interpret) — see this module's own `README.md`.

---

## 2. Supported input classes (V1)

- Digital PDF (embedded text layer).
- Scanned/image-based PDF (no usable text layer — requires document extraction).
- JPG/PNG (typically a photographed document).
- Multiple images/files that together form **one** invoice (e.g. several photos of one paper document, or a multi-page scan split into separate image files).
- A structured connector/API payload (a source system that already exposes invoice data as structured fields, requiring no document extraction at all).

**Explicitly not an input format:** email. Email is a transport/delivery mechanism, not a document format — an email's *attachment* is handled according to its own actual format (PDF, JPG, etc.), per the classes above. Building the email-fetching/attachment-extraction mechanism itself is out of scope for V1 (§13).

**Explicitly out of scope for V1:** a QuickBooks-specific acquisition connector. The Invoice Source Contract (§3) is designed so a QuickBooks connector (or any other structured-connector source) can be added later without changing the contract, but no such connector is built or specified here.

---

## 3. Invoice Source Contract

A small, provider-agnostic contract is the seam between "how a document/payload was acquired" and "what Invoice Intake does with it." Its purpose is to let two structurally different acquisition paths converge on the exact same downstream processing:

- **Unstructured path** — one or more source files (PDF/JPG/PNG) with no pre-existing structured data. These are processed via **document extraction** (OCR/layout+field extraction, §4) to produce field-level data.
- **Structured path** — a connector/API payload that already carries invoice data as structured fields (e.g. a supplier system exposing invoices via API). These **bypass document extraction entirely** — there is no OCR step to run, because the fields already exist.

Both paths converge on the same downstream shape: a single `InvoiceSourceSubmission` handed to the rest of the agent, minimally carrying:
- `source_kind`: `UNSTRUCTURED_DOCUMENT` or `STRUCTURED_PAYLOAD`.
- `source_items`: the file(s) (unstructured path) or the payload (structured path) — see §5 for what must be preserved from each.
- `invoking_domain_reference`: an opaque identifier the invoking Domain supplies so the eventual result can be returned to the right place (§10) — Invoice Intake never interprets this reference, only carries it through.
- `submitted_at`: acquisition timestamp (§5).

Whichever path is taken, the agent's output is always the same `NormalizedInvoice` (§7) — the invoking Domain never needs to know or care which path produced it.

---

## 4. Document extraction provider

**Initial provider (V1): AWS Textract, using the `AnalyzeExpense` API** for the unstructured-document path (§2, §3).

RF-One must remain **provider-agnostic at the agent boundary** — nothing outside the document-extraction step may depend on Textract-specific request/response shapes, field names, or confidence semantics. The extraction step's job is exactly this: take a source file, call whichever provider is currently configured, and produce the provider-agnostic `NormalizedInvoice` (§7) plus the preserved raw response (§5/§6). Swapping the provider later (a different OCR/document-AI vendor) must not require changing anything downstream of this step.

The structured-connector path (§3) never calls this provider at all — it has no document to extract from.

---

## 5. Source preservation

For every submission, Invoice Intake always preserves, unmodified:

- The **original source file(s)** (unstructured path) or the **original source payload** (structured path) — exactly as received, never altered, never re-encoded, never partially discarded.
- The **raw provider response** (the unstructured path's raw Textract/`AnalyzeExpense` output; the structured path's raw connector payload, which is itself both the source and the "provider response" since no separate extraction call occurs).
- **Source metadata** — at minimum: originating file name(s)/identifiers, file type(s)/MIME type(s), size(s), the invoking Domain's own reference (§3), and (for a multi-file submission) the grouping that ties the files together as one invoice.
- **Acquisition timestamp** — when Invoice Intake received the submission, independent of the invoice's own dates (§7).

Nothing here is ever silently discarded, downsampled, or summarized in place of the original.

---

## 6. Provider Mirror

Raw provider/connector output (the Textract response, or the structured payload as received) is preserved exactly as fetched — for audit, debugging, and reprocessing (e.g. re-running normalization against the same raw response after a normalization-logic improvement, without re-acquiring the source). This mirrors the same Provider Mirror principle already established for the Clover connector's `SourceRecord` (append-only, provider-shaped, never the API a consuming Domain reads).

**No consuming Domain may depend directly on provider-specific raw structures.** A Domain reads only the `NormalizedInvoice` (§7); the raw mirror exists purely as Invoice Intake's own internal audit/recovery asset, exactly as `SourceRecord` is never read by a Domain in the Clover connector.

---

## 7. NormalizedInvoice

The provider-agnostic structure every submission — unstructured or structured — produces. It preserves **all invoice information materially present in the source**, not only whatever fields a currently-known consuming Domain happens to use today (§7 rule, restated: never discard information because a later Domain may not need it yet).

Every field below is Optional/Unknown unless the source actually provided it — nothing is defaulted or invented (§8's "never invents missing values" applies here structurally, not only at the lifecycle-decision level).

**Header**
- Supplier identity/name, exactly as extracted (a raw fact, not a resolved/validated Supplier identity — see §9).
- Invoice number.
- Invoice date.
- Due date, if present.
- Currency (§11 — never assumed/defaulted to any one currency).
- Purchase order / reference number(s), if present.

**Lines** (one entry per line item; a submission may have zero lines if none were extractable — never fabricated)
- Description.
- Supplier product/item code, if present.
- Quantity.
- Unit.
- Unit price.
- Discount, if present.
- Tax, if present.
- Fees/charges, if present.
- Line total.
- Any other line-level information materially present in the source that does not fit the fields above — preserved rather than dropped (see "Open items" §15 for how this is represented).

**Totals**
- Subtotal.
- Discounts.
- Tax.
- Fees/charges.
- Total.
- Any other explicitly-present total (e.g. a supplier-specific total category) — preserved, not forced into one of the categories above.

**Metadata**
- Reference to the source file(s)/payload (§5) — not the content itself, a pointer to the preserved original.
- Language (of the source document/payload — §11).
- Extraction confidence (§8) — document-level and, where the provider supports it, field/line-level.
- Review status (§8's lifecycle state).
- Version (§12).
- Audit metadata (who/what performed extraction, when, which provider/version acquired it, when each lifecycle transition occurred).

---

## 8. Lifecycle

```
RECEIVED → EXTRACTED → (READY | NEEDS_REVIEW) → APPROVED
```

- **RECEIVED** — the `InvoiceSourceSubmission` (§3) has arrived and its source/raw response are preserved (§5/§6); extraction has not yet run (or, structured path, has been bypassed).
- **EXTRACTED** — a `NormalizedInvoice` (§7) exists, produced by document extraction (§4) or directly from the structured payload (§3).
- **READY** — reached only when the invoicing supplier/source is trusted/validated (§9) **and** extraction confidence is high **and** the extracted data is internally coherent (e.g. line totals reconcile with the stated total, within a tolerance this spec does not fix — see Open items). READY may be reached without mandatory manual review.
- **NEEDS_REVIEW** — reached whenever the supplier/source is unknown or not yet validated, confidence is low, required values are missing, or an internal inconsistency is found. For V1, every unresolved exception in this state requires human review before the invoice can advance — there is no V1 auto-resolution path.
- **APPROVED** — the terminal, confirmed state (reached directly from READY, or from NEEDS_REVIEW once a human has reviewed/corrected it). Only an APPROVED `NormalizedInvoice` is returned to the invoking Domain (§10).

**RF-One never invents missing values at any lifecycle stage** — a field the source did not provide stays absent/Unknown all the way through APPROVED; it is never filled in with a guess, a default, or an inferred value, matching the same discipline already established in the current InvoiceIntake prototype's parser and bridge code.

---

## 9. Supplier validation

Invoice Intake must support determining whether the invoicing supplier/source is currently considered **trusted/reliable** — this determination is one of the inputs the lifecycle (§8) uses to decide READY vs. NEEDS_REVIEW.

This specification deliberately does **not** define what makes a supplier trustworthy in business terms, how trust is earned/revoked, or any Purchasing-specific supplier record/economics — that is Purchasing's own domain knowledge (already owned by `01 Domains/Business Domain/Restaurant/Purchasing/`, e.g. its own `Supplier` concept), explicitly excluded here (§13). Invoice Intake only needs a way to **ask** "is this supplier/source trusted?" and receive an answer usable by §8 — the answer's source of truth, and the criteria behind it, belong to whichever Domain(s) maintain that knowledge, most likely via the same invocation/adapter relationship described in §10, not a new capability invented inside Invoice Intake.

---

## 10. Invocation/return model

**The Business Domain invokes Invoice Intake** — Invoice Intake is never self-triggered by a document simply arriving somewhere, and it never independently decides which Domain, Purchase Document, or business record an invoice belongs to. The invoking Domain supplies its own reference (§3) at submission time specifically so Invoice Intake never has to guess this.

After an invoice reaches **APPROVED** (§8):
- The approved `NormalizedInvoice` is returned/persisted to the invoking Domain through its own adapter/contract (a Domain-specific bridge, analogous to the current `purchasing_bridge.py`'s role, but built against the provider-agnostic `NormalizedInvoice`/Invoice Source Contract rather than the current OCR-and-parser-specific dict shapes).
- The invoking Domain remains fully responsible for its own business model and consequences — classification, costing, reconciliation, accounting, tax treatment, or anything else it chooses to do with the normalized data is entirely outside Invoice Intake's concern from this point on.

---

## 11. Multi-language / multi-currency

Native design requirement, not a later extension. No field, prompt, or default anywhere in this specification assumes English text or USD currency:
- `Currency` (§7) is always read from the source, never defaulted to any specific currency when absent — an invoice with no discernible currency stays Unknown, exactly like any other missing field (§8).
- `Language` (§7, Metadata) is a recorded fact about the source document, not a constraint on which languages the agent can process — the document-extraction provider (§4) and any future provider swap must be evaluated for multi-language capability, but this specification does not restrict Invoice Intake to any single language's document formats or number/date conventions.

---

## 12. Corrections/versioning

An **APPROVED** `NormalizedInvoice` is never silently overwritten. A later correction — whether discovered by the invoking Domain or by a subsequent Invoice Intake reprocessing — creates a **new version**, with:
- A full audit trail of what changed and why (or by whom, if a manual correction).
- The **prior version(s) preserved**, not deleted or replaced in place.
- The `version` metadata field (§7) distinguishing which version is current/authoritative.

This mirrors the same "never rewrite history, add a superseding record instead" principle already used elsewhere in RF-One's own approved conventions (e.g. immutable task reports, `superseded_by_*` fields on Payroll runs).

---

## 13. Explicit exclusions

This specification deliberately does **not** define, and no future implementation of it may silently redefine, any of the following (all remain exclusively owned elsewhere or explicitly not built in V1):

- Restaurant/Purchasing models.
- Supplier economic meaning (what a supplier's pricing/terms mean for cost or margin).
- `PurchaseDocument`/`PurchaseLine` (canonical entities now owned by Purchased, consumed by Restaurant/Purchasing — see Purchased/README.md, "Invoice Intake alignment (closed)").
- Effective Product Cost.
- Reconciliation (Order vs. Invoice vs. Receiving, or any other business reconciliation).
- Accounting/tax treatment (see also the still-open "Invoice Tax Treatment" question in `OpenQuestions.md`, unaffected by this spec).
- A QuickBooks connector.
- An email-ingestion implementation (only the "email is not itself an invoice format" boundary is stated, per §2).

---

## 14. Relationship to the current `03 Software/InvoiceIntake/` prototype

Not a rule, a factual note for implementers: the current prototype (`ocr_engine.py`, `parser.py`, `purchased_bridge.py` — renamed from `purchasing_bridge.py` by "Align legacy Invoice Intake with Purchased"; see `07 Tasks/Reports/INVOICE_INTAKE_MULTI_FORMAT_CAPABILITY_AUDIT` findings, reported in-conversation) already implements a narrower, single-provider (Tesseract), single-file version of the acquisition idea this specification generalizes, now saving through Purchased's canonical persistence rather than a Purchasing-owned one (see Purchased/README.md, "Invoice Intake alignment (closed)"). It is not redesigned, extended, or replaced by this document — this is a specification for the target V1 agent, not an instruction to modify that prototype.

---

## 15. Open items

Design decisions this V1 specification deliberately leaves unresolved (see also the report's own "Unresolved design decisions" list):

- The exact coherence/tolerance rule that decides "internally coherent" for READY (§8) — e.g. how large a subtotal/total mismatch is still acceptable — is not fixed here.
- The exact confidence threshold(s) that separate "high confidence" from "low confidence" (§8) are not fixed here, nor is whether they are provider-specific (Textract's own confidence scale) or normalized to a provider-agnostic scale.
- The exact mechanism by which a Domain answers Invoice Intake's supplier-trust question (§9) — a synchronous call, a pre-shared list, an event — is not specified; only that Invoice Intake must be able to ask and receive an answer.
- Any material information that does not fit the named Header/Lines/Totals fields (§7's "all other materially present line-level information" / "any other totals explicitly present") is described as something that must be preserved, but this specification does not fix its concrete representation (e.g. a generic key-value extension map vs. a fixed extended-field list).
