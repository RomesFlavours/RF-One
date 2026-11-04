"""Schema/data-discovery analysis and Markdown report generation.

This module never reads or writes field *values* for known PII-bearing
fields (customer name/email/phone, payment card identifiers) into the
report — only field names, types, presence counts and aggregate
timestamps. It performs no tip calculation and no KPI derivation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Field-name substrings that, if present as *values* in the report, would
# leak PII. We only ever report field names/types/counts below, never
# values, but this list documents the fields deliberately excluded from
# even indirect summarization (e.g. no "most common value" statistics).
PII_FIELD_HINTS = (
    "name",
    "email",
    "phone",
    "address",
    "card",
    "last4",
    "ssn",
    "dob",
    "birthdate",
)

TIP_RELEVANT_HINTS = (
    "tip",
    "amount",
    "tax",
    "tender",
    "employee",
    "refund",
    "void",
    "result",
    "created",
    "modified",
    "cash",
    "gratuity",
)

TIMESTAMP_NAME_HINT = "time"


def _python_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        if set(value.keys()) == {"id"}:
            return "reference(id)"
        return "object"
    return type(value).__name__


def _looks_like_pii_field(field_name: str) -> bool:
    lowered = field_name.lower()
    return any(hint in lowered for hint in PII_FIELD_HINTS)


def _looks_like_epoch_millis(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 10**11 < value < 10**14


def summarize_fields(elements: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    total = len(elements)
    fields: dict[str, dict[str, Any]] = {}

    for element in elements:
        if not isinstance(element, dict):
            continue
        for key, value in element.items():
            info = fields.setdefault(
                key,
                {"types": set(), "present_count": 0},
            )
            info["present_count"] += 1
            info["types"].add(_python_type_name(value))

    summary = {}
    for key, info in fields.items():
        summary[key] = {
            "types": sorted(info["types"]),
            "present_count": info["present_count"],
            "present_ratio": round(info["present_count"] / total, 3) if total else 0.0,
        }
    return summary


def earliest_latest_timestamps(elements: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    timestamps: list[int] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        for key, value in element.items():
            if TIMESTAMP_NAME_HINT in key.lower() and _looks_like_epoch_millis(value):
                timestamps.append(value)
    if not timestamps:
        return None, None
    earliest = datetime.fromtimestamp(min(timestamps) / 1000, tz=timezone.utc).isoformat()
    latest = datetime.fromtimestamp(max(timestamps) / 1000, tz=timezone.utc).isoformat()
    return earliest, latest


def relationship_fields(field_summary: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(name for name, info in field_summary.items() if "reference(id)" in info["types"])


def tip_relevant_fields(field_summary: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        name
        for name in field_summary
        if any(hint in name.lower() for hint in TIP_RELEVANT_HINTS)
    )


def format_collection_section(
    name: str, category: str, manifest_entry: dict[str, Any], elements: list[dict[str, Any]] | None
) -> str:
    lines = [f"### {category} — `{name}`", ""]

    if elements is None:
        lines.append("- **Status:** failed / not available")
        lines.append(f"- **Attempted endpoint:** `{manifest_entry.get('path', '')}`")
        if manifest_entry.get("http_status_last") is not None:
            lines.append(f"- **HTTP status:** {manifest_entry['http_status_last']}")
        if manifest_entry.get("error"):
            lines.append(f"- **Error:** {manifest_entry['error']}")
        lines.append("")
        return "\n".join(lines)

    field_summary = summarize_fields(elements)
    earliest, latest = earliest_latest_timestamps(elements)
    relationships = relationship_fields(field_summary)
    tip_fields = tip_relevant_fields(field_summary)
    pagination_used = manifest_entry.get("pages_fetched", 0) > 1

    lines.append(f"- **Endpoint:** `{manifest_entry.get('path', '')}`")
    lines.append(f"- **Record count:** {len(elements)}")
    lines.append(f"- **Pages fetched:** {manifest_entry.get('pages_fetched', 0)} (pagination required: {'yes' if pagination_used else 'no'})")
    if manifest_entry.get("truncated_by_safety_guard"):
        lines.append("- **Warning:** stopped by the internal pagination safety guard — collection may be incomplete.")
    if earliest or latest:
        lines.append(f"- **Earliest timestamp observed:** {earliest or 'n/a'}")
        lines.append(f"- **Latest timestamp observed:** {latest or 'n/a'}")
    else:
        lines.append("- **Timestamps:** none of the common `*time*` epoch-millis fields were found")

    if field_summary:
        lines.append("- **Top-level fields observed:**")
        for field_name in sorted(field_summary):
            info = field_summary[field_name]
            types = ",".join(info["types"])
            pii_marker = " — PII-like field name, value withheld from this report" if _looks_like_pii_field(field_name) else ""
            lines.append(f"  - `{field_name}` ({types}), present in {info['present_ratio'] * 100:.0f}% of records{pii_marker}")
    else:
        lines.append("- **Top-level fields observed:** none (empty collection)")

    if relationships:
        lines.append(f"- **Relationship-shaped fields (nested `{{id}}` references):** {', '.join(f'`{r}`' for r in relationships)}")

    if tip_fields:
        lines.append(f"- **Fields potentially relevant to tips/payments analysis:** {', '.join(f'`{t}`' for t in tip_fields)}")

    if manifest_entry.get("notes"):
        lines.append(f"- **Notes:** {manifest_entry['notes']}")

    lines.append("")
    return "\n".join(lines)


def write_discovery_report(
    report_path: Path,
    manifest: dict[str, Any],
    collections_data: dict[str, list[dict[str, Any]] | None],
    merchant_data: dict[str, Any] | None,
) -> Path:
    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = []
    lines.append("# Clover Data Discovery Report")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Environment: {manifest.get('environment')}  ")
    lines.append(f"Base URL: `{manifest.get('base_url')}`  ")
    lines.append(f"Merchant ID: `{manifest.get('merchant_id')}`  ")
    lines.append(f"Export run: `{manifest.get('export_start_time')}` → `{manifest.get('export_completion_time')}`")
    lines.append("")
    lines.append(
        "This report is schema/discovery oriented. It never includes customer names, emails, "
        "phone numbers, payment identifiers or other PII values — only field names, types, "
        "presence counts and aggregate timestamps."
    )
    lines.append("")
    lines.append("Tip calculation, KPI derivation and Restaurant-domain normalization are explicitly "
                  "out of scope for this report (TASK_CLOVER_001).")
    lines.append("")

    lines.append("## Merchant")
    lines.append("")
    if merchant_data:
        merchant_fields = summarize_fields([merchant_data])
        lines.append(f"- **Merchant ID:** `{merchant_data.get('id', manifest.get('merchant_id'))}`")
        if "name" in merchant_data:
            lines.append("- **Merchant name field present:** yes (value withheld from this report)")
        lines.append("- **Top-level fields observed:**")
        for field_name in sorted(merchant_fields):
            info = merchant_fields[field_name]
            pii_marker = " — PII-like field name, value withheld from this report" if _looks_like_pii_field(field_name) else ""
            lines.append(f"  - `{field_name}` ({','.join(info['types'])}){pii_marker}")
    else:
        lines.append("- Merchant call failed — see manifest.json for status/error.")
    lines.append("")

    entries_by_name = {e["name"]: e for e in manifest.get("collections", []) if e["name"] != "merchant"}

    lines.append("## Collections")
    lines.append("")
    for name, entry in entries_by_name.items():
        elements = collections_data.get(name)
        lines.append(format_collection_section(name, entry.get("category", ""), entry, elements))

    orders_sample_size = manifest.get("orders_line_item_completeness_sample_size", 0)
    if orders_sample_size:
        lines.append("## Orders line-item completeness sample")
        lines.append("")
        lines.append(
            f"A bounded sample of {orders_sample_size} order(s) was checked by comparing the "
            "`expand=lineItems` array returned on the `orders` collection against a direct call to "
            "that order's own `line_items` endpoint. See "
            "`orders_line_item_completeness_sample.json` in the raw export directory for the "
            "per-order comparison. Do not assume the full order history's expanded line items are "
            "complete based on this sample alone."
        )
        lines.append("")

    lines.append("## Known limitations")
    lines.append("")
    lines.append("- Pagination uses `limit`/`offset`; a page shorter than the requested page size is "
                  "treated as the last page (Clover does not reliably return a total count).")
    lines.append("- Nested `expand`-ed collections (e.g. order `lineItems`, `modifier_groups` → "
                  "`modifiers`) can be truncated independently of the parent collection's own "
                  "pagination; only a bounded sample of orders was cross-checked against their "
                  "dedicated `line_items` endpoint in this pass.")
    lines.append("- No date-range filter was applied; the exporter attempted the complete accessible "
                  "history for every collection. Any endpoint-imposed history limit is recorded per "
                  "collection above via HTTP status/error where encountered.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
