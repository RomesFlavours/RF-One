"""Forward the historical launcher to the current local Selection runtime."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "AWSSelection/Selection"
    sys.path.insert(0, str(target))
    runpy.run_path(str(target / "local_server.py"), run_name="__main__")
