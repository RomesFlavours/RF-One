"""Pagination support for Clover list endpoints.

Clover collection endpoints page with `limit`/`offset` query parameters and
return `{"elements": [...], "href": "..."}`. Clover does not reliably return
a total count, so completeness is detected by requesting one page beyond a
short page (fewer elements than the requested limit means it was the last
page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import CloverClient, CloverGetResult

# Clover's documented maximum `limit` for most v3 collection endpoints is
# 1000. Per TASK_CLOVER_001 ("use a large legal page size ... up to the
# documented maximum"), this is used as the default page size. An endpoint
# that rejects this limit (HTTP 400) simply fails that one collection —
# the exporter tolerates partial API coverage rather than guessing a
# smaller size per endpoint.
DEFAULT_PAGE_SIZE = 1000

# Safety guard against an unexpected infinite-pagination bug (e.g. a Clover
# response that never shrinks below the page size). This is not a business
# limit — 500 pages at the max page size is 500,000 records.
MAX_PAGES_SAFETY_GUARD = 500


@dataclass
class PaginationResult:
    path: str
    ok: bool
    elements: list[dict[str, Any]] = field(default_factory=list)
    pages_fetched: int = 0
    error: str | None = None
    error_status_code: int | None = None
    truncated_by_safety_guard: bool = False


def paginate(
    client: CloverClient,
    path: str,
    extra_params: dict[str, Any] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> PaginationResult:
    """Retrieve every element of a Clover collection endpoint.

    Does not assume the first page is the complete dataset: it keeps
    requesting subsequent offsets until a page returns fewer elements than
    `page_size`, or an error/empty page is encountered.
    """
    elements: list[dict[str, Any]] = []
    offset = 0
    pages_fetched = 0
    params_base = dict(extra_params or {})

    while True:
        if pages_fetched >= MAX_PAGES_SAFETY_GUARD:
            return PaginationResult(
                path=path,
                ok=True,
                elements=elements,
                pages_fetched=pages_fetched,
                truncated_by_safety_guard=True,
            )

        params = dict(params_base)
        params["limit"] = page_size
        params["offset"] = offset

        result: CloverGetResult = client.get(path, params=params)
        if not result.ok:
            if pages_fetched > 0:
                # Partial success: keep what was already retrieved, but
                # surface the failure so the manifest records it honestly.
                return PaginationResult(
                    path=path,
                    ok=False,
                    elements=elements,
                    pages_fetched=pages_fetched,
                    error=f"pagination failed after {pages_fetched} page(s): {result.error}",
                    error_status_code=result.status_code,
                )
            return PaginationResult(
                path=path,
                ok=False,
                elements=elements,
                pages_fetched=pages_fetched,
                error=result.error,
                error_status_code=result.status_code,
            )

        page_data = result.data if isinstance(result.data, dict) else {}
        page_elements = page_data.get("elements")
        if page_elements is None:
            page_elements = []
        if not isinstance(page_elements, list):
            return PaginationResult(
                path=path,
                ok=False,
                elements=elements,
                pages_fetched=pages_fetched,
                error="unexpected response shape: 'elements' is not a list",
            )

        pages_fetched += 1
        elements.extend(page_elements)

        if len(page_elements) < page_size:
            break
        offset += page_size

    return PaginationResult(path=path, ok=True, elements=elements, pages_fetched=pages_fetched)
