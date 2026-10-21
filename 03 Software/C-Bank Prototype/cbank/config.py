"""C-Bank Prototype configuration — every path in one place.

The prototype READS the operational Bank (database and code) and WRITES only
to its own experimental store. Nothing here points a writer at Bank.
"""
import os
from pathlib import Path

_LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))

# Operational Bank working database (read-only, opened with mode=ro).
BANK_DB = Path(os.environ.get("CBANK_BANK_DB", _LOCAL / "RF-One" / "Bank" / "rfone.db"))

# Operational Bank code whose models match BANK_DB (imported, never modified).
BANK_CODE_ROOT = Path(os.environ.get(
    "CBANK_BANK_CODE_ROOT",
    Path(__file__).resolve().parents[4] / "rf-one-bank-simple-who-rules"))

# Experimental store: results, human decisions, AI investigations, exports.
STORE_DIR = Path(os.environ.get("CBANK_STORE_DIR", _LOCAL / "RF-One" / "C-Bank"))
STORE_DB = STORE_DIR / "cbank.db"
EXPORT_DIR = STORE_DIR / "exports"

HOST = "127.0.0.1"
PORT = int(os.environ.get("CBANK_PORT", "5090"))

# Display timezone for timestamps shown to a person (RF-One UI rule 1).
DISPLAY_TZ = "America/New_York"

# Automatic acceptance thresholds (decision 05: classify new cases only when
# the evidence is sufficiently reliable).
MEMORY_MIN_PRECEDENTS = 2      # concordant human precedents for MEMORY
AI_MIN_CONFIDENCE = 0.85       # AI confidence for an automatic classification
