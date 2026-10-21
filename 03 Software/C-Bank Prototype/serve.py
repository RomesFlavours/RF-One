"""Start the C-Bank Prototype on http://127.0.0.1:5090 (local only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbank import config  # noqa: E402
from cbank.web import create_app  # noqa: E402

if __name__ == "__main__":
    print(f"C-Bank Prototype — Bank read-only: {config.BANK_DB}")
    print(f"Experimental store: {config.STORE_DB}")
    print(f"Open http://{config.HOST}:{config.PORT}/")
    create_app().run(host=config.HOST, port=config.PORT, debug=False)
