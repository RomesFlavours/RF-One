"""Local storage of the CV Selection SP prototype.

No new database (RF-One local database policy): each position is one JSON
file next to its original CV files, in %LOCALAPPDATA%\\RF-One\\CV Selection SP
(outside OneDrive and Git; SP_DATA_DIR overrides it for tests). The JSON keeps
the approved requirement versions and, for every CV, the extracted text and
the full verified analysis with its prompt, profile and requirement versions,
so every ranking can be traced back to what produced it.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.environ.get("SP_DATA_DIR") or
            Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "CV Selection SP")
LOCK = threading.RLock()
_cache: dict[str, dict] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def _dir(pid: str) -> Path:
    return DATA / "positions" / pid


def cv_dir(pid: str) -> Path:
    path = _dir(pid) / "cv"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(position: dict) -> None:
    with LOCK:
        path = _dir(position["id"])
        path.mkdir(parents=True, exist_ok=True)
        tmp = path / "position.json.tmp"
        tmp.write_text(json.dumps(position, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path / "position.json")
        _cache[position["id"]] = position


def load(pid: str) -> dict | None:
    with LOCK:
        if pid in _cache:
            return _cache[pid]
        path = _dir(pid) / "position.json"
        if not path.exists():
            return None
        _cache[pid] = json.loads(path.read_text(encoding="utf-8"))
        return _cache[pid]


def all_positions() -> list[dict]:
    root = DATA / "positions"
    if not root.exists():
        return []
    found = [load(p.name) for p in root.iterdir() if (p / "position.json").exists()]
    return sorted([p for p in found if p], key=lambda p: p["created_at"], reverse=True)
