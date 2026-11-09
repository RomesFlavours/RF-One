"""Resolve the existing RF-One modules; never create a database at import."""
import sys
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOFTWARE / 'RF-One Data Store'))
sys.path.insert(0, str(SOFTWARE / 'Clover Data Explorer'))
