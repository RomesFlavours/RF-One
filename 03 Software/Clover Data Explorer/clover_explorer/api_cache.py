"""Disk-backed cache for supplementary read-only GET calls.

TASK_CLOVER_001's raw export did not request every expansion this task
needs (e.g. `cardTransaction` on payments, `modifications` on line items —
see CLOVER_EXPORT_MAPPING.md). Rather than mutate the original immutable
raw export, this task issues additional GET-only calls and caches each
response to a local, Git-ignored file so repeated runs of the exporter
during development do not re-hit the live Clover API unnecessarily.

The cache lives under `data/generated_exports/_api_cache/`, itself inside
the Git-ignored `data/generated_exports/` tree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename(key: str) -> str:
    return _SAFE_CHARS.sub("_", key) + ".json"


class ApiCache:
    def __init__(self, cache_dir: Path, namespace: str):
        self.dir = cache_dir / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    def get_or_fetch(self, key: str, fetch: Callable[[], Any]) -> Any:
        path = self.dir / _safe_filename(key)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        value = fetch()
        path.write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
        return value
