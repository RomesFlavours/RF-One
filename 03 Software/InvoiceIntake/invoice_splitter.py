"""Multi-invoice PDF splitting ("Purchased Supplier Training — Phase 2").

Phase 1 always treated one physical source file as one PurchaseDocument.
Real documents showed that is wrong for at least two suppliers:

- **Prime Line Distributors**: a single PDF can bundle several distinct
  invoices as separate pages (`PL20200609171959_001.pdf`: 4 pages, 4
  distinct invoices, each with its own Number/Date/Total).
- **Ben E. Keith Foods**: a single PDF can bundle several distinct invoices
  too, but one of them spans *more than one page*
  (`24 Keith_20241010_0002-1-3.pdf`: 3 pages, 2 invoices — the second one
  is pages 2-3).

So the rule is **one physical PDF != one PurchaseDocument**, but also
**one page != one invoice** — this module decides where one invoice ends
and the next begins, working at PAGE granularity (a boundary can only ever
fall *between* two pages, never inside one) using a single, generic
algorithm:

    for each page, extract its own document_number (reusing the exact same
    generic-parser + supplier_format_rules specialization pipeline already
    used for a whole document)
    -> a page whose own number is present and DIFFERENT from the currently
       open invoice's number starts a NEW invoice
    -> a page whose own number is blank, or the SAME as the currently open
       invoice's, is a CONTINUATION of it (Ben E. Keith's own multi-page
       case)

This is deliberately supplier-agnostic — it is the exact same
`document_number` extraction already trusted per-document, just applied
per-page instead. The one Supplier-specific addition needed to make this
work at all is `supplier_format_rules._KEITH_INVOICE_NUMBER` (Ben E.
Keith's own "Invoice No. | Page | Rep" table row survives even where the
page's brand text itself came back too scrambled to recognize — see that
module for why), which the task's own instructions explicitly allow
("Supplier-specific hints sono ammessi solo se necessari").

**Uncertainty rule (Task requirement 4): "Meglio una review umana che
creare 2 PurchaseDocument sbagliati."** `split_into_invoices()` returns
`None` — meaning "do not split; keep the legacy single-document
behavior" — whenever it cannot assign every resulting invoice a real
identity:

- fewer than 2 pages (nothing to split);
- no page ever showed a document_number different from another (no
  boundary evidence at all);
- ANY resulting segment has no document_number on ANY of its pages (a
  segment with zero identity evidence is exactly the ambiguous case this
  module must never guess through — see module docstring's "Meglio...").

It never invents a boundary and never invents a document_number — when
uncertain, the whole file is left as a single document, exactly like
before this module existed, and normal NORMALIZED/HUMAN validation (which
already requires a recognized document_number) takes over from there.
"""

from __future__ import annotations

from dataclasses import dataclass

import parser as invoice_parser
import supplier_format_rules


@dataclass(frozen=True)
class InvoiceSegment:
    page_start: int  # 1-indexed, inclusive
    page_end: int  # 1-indexed, inclusive
    total_pages: int
    segment_index: int  # 1-indexed among the segments returned together
    segment_count: int
    text: str  # this segment's own pages, joined -- what parser.py/supplier_format_rules run against
    document_number: str  # the value that anchored this segment's boundary (never blank -- see module docstring)

    @property
    def is_multi_page(self) -> bool:
        return self.page_end > self.page_start

    @property
    def page_range_label(self) -> str:
        return f"p{self.page_start}" if not self.is_multi_page else f"p{self.page_start}-{self.page_end}"


def _page_document_number(page_text: str) -> str:
    """The same document_number a single-page document would get: the
    generic parser's own guess, refined by whatever Supplier+Format
    specialization recognizes this page (Task requirement 3: reuse real
    evidence, do not reinvent a separate detector)."""

    generic_header = {
        "supplier_name": invoice_parser.guess_supplier(page_text.splitlines()),
        "document_number": invoice_parser.guess_document_number(page_text),
        "issue_date": "",
        "currency": "",
        "total_amount": "",
    }
    specialized = supplier_format_rules.apply_supplier_specializations(page_text, generic_header)
    return (specialized.get("document_number") or "").strip()


def split_into_invoices(pages: list[str]) -> list[InvoiceSegment] | None:
    """`pages` is a source file's own per-page text (see
    `ocr_engine.extract_pages_from_pdf`). Returns `None` when this file
    should NOT be split (see module docstring's "Uncertainty rule")."""

    if len(pages) <= 1:
        return None

    raw_segments: list[dict] = []
    for index, page_text in enumerate(pages, start=1):
        page_number = _page_document_number(page_text)
        if not raw_segments:
            raw_segments.append(
                {"start": index, "end": index, "pages": [page_text], "number": page_number, "has_blank_page": not page_number}
            )
            continue

        current = raw_segments[-1]
        if page_number and current["number"] and page_number != current["number"]:
            # A confidently different, non-blank number -- a real new invoice.
            raw_segments.append(
                {"start": index, "end": index, "pages": [page_text], "number": page_number, "has_blank_page": not page_number}
            )
        else:
            # Either this page's own number matches the current invoice, or
            # it has none of its own (a Ben E. Keith-style continuation
            # page, or a page this module simply cannot read a number from
            # at all) -- tentatively part of the current invoice. Which one
            # it actually was only matters if a REAL boundary is found
            # later while this segment still has an unresolved blank page
            # in it -- see the ambiguity check below.
            current["end"] = index
            current["pages"].append(page_text)
            if not current["number"] and page_number:
                current["number"] = page_number
            if not page_number:
                current["has_blank_page"] = True

    if len(raw_segments) <= 1:
        return None  # no page ever disagreed with another -- nothing to split

    if any(not segment["number"] for segment in raw_segments):
        return None  # at least one resulting invoice has no identity evidence at all -- ambiguous, do not guess

    # A segment that had to absorb at least one blank/unreadable page AND is
    # followed by another real segment is untrustworthy: a real boundary
    # WAS found somewhere in this file, so that blank page could just as
    # plausibly have belonged to the FOLLOWING invoice instead of this one
    # -- exactly the "Meglio una review umana che creare 2 PurchaseDocument
    # sbagliati" case (Task requirement 4). A trailing blank page in the
    # LAST segment is fine (nothing else it could belong to).
    for position, segment in enumerate(raw_segments):
        if segment["has_blank_page"] and position < len(raw_segments) - 1:
            return None

    return [
        InvoiceSegment(
            page_start=segment["start"],
            page_end=segment["end"],
            total_pages=len(pages),
            segment_index=position,
            segment_count=len(raw_segments),
            text="\n".join(segment["pages"]),
            document_number=segment["number"],
        )
        for position, segment in enumerate(raw_segments, start=1)
    ]
