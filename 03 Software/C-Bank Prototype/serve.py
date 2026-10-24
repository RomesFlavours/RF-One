"""Start the C-Bank Prototype on http://127.0.0.1:5090 (local only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402

from cbank import config, service  # noqa: E402
from cbank.web import create_app  # noqa: E402

if __name__ == "__main__":
    print(f"C-Bank Prototype — Bank read-only: {config.BANK_DB}")
    print(f"Experimental store: {config.STORE_DB}")
    print(f"Open http://{config.HOST}:{config.PORT}/")
    app = create_app()
    if os.environ.get("CBANK_AUTO_RUN", "1") != "0":
        # After a new Bank import a full run starts by itself (read-only check every minute).
        service.start_auto_runs(app.config["CON"])
    app.run(host=config.HOST, port=config.PORT, debug=False)
