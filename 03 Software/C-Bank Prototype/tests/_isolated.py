"""Every C-Bank test runs on a COPY of the Bank database (Phase 3A: the engine and a person's decision
write into the Bank database itself). Imported first by each test module; `CBANK_BANK_DB` given by the
caller is used as it is, otherwise the operational database is copied with SQLite's backup API (consistent
even while Bank runs) into a temporary folder removed at exit."""
import atexit
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

if not os.environ.get("CBANK_BANK_DB"):
    _source = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
    _folder = tempfile.mkdtemp(prefix="cbank_tests_")
    _copy = Path(_folder) / "rfone.db"
    _src = sqlite3.connect(f"file:{_source.as_posix()}?mode=ro", uri=True)
    _dst = sqlite3.connect(_copy)
    _src.backup(_dst)
    _dst.close()
    _src.close()
    os.environ["CBANK_BANK_DB"] = str(_copy)
    atexit.register(shutil.rmtree, _folder, ignore_errors=True)
