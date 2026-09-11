"""Reads the one canonical copy of the dish content (`dish-data` JSON already
approved inside `RF-One-Training.html`) so a pill's study page can display
it without ever keeping a second, hand-maintained copy that could drift
from `/training/menu` (spec §3 — "Riusa i contenuti senza mantenere copie
manuali divergenti").
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

_HTML_PATH = Path(__file__).resolve().parent / "RF-One-Training.html"
_SCRIPT_RE = re.compile(
    r'<script id="dish-data" type="application/json">(.*?)</script>', re.DOTALL
)

_lock = threading.Lock()
_cache: dict[str, dict] | None = None
_cache_mtime: float | None = None


def _parse() -> dict[str, dict]:
    html = _HTML_PATH.read_text(encoding="utf-8")
    match = _SCRIPT_RE.search(html)
    if match is None:
        raise RuntimeError(f"dish-data script block not found in {_HTML_PATH}")
    dishes = json.loads(match.group(1))
    return {d["id"]: d for d in dishes}


def load_dishes() -> dict[str, dict]:
    """Returns `{dish_id: dish_dict}`, cached and refreshed automatically if
    the source file's mtime changes (so an edit to the approved content is
    picked up on the next request without an app restart, exactly like
    `/training/menu` already reflects it — no separate reload step for two
    supposedly-identical copies to fall out of sync over)."""
    global _cache, _cache_mtime
    mtime = _HTML_PATH.stat().st_mtime
    with _lock:
        if _cache is None or _cache_mtime != mtime:
            _cache = _parse()
            _cache_mtime = mtime
        return _cache


def get_dish(dish_id: str) -> dict | None:
    return load_dishes().get(dish_id)
