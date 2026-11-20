"""Local launcher: serves BBC Wine on 127.0.0.1 only, with automatic sign-in
as the local administrator (open /local/start). Settings come from
%LOCALAPPDATA%\\BBC Wine\\local.json, written by setup_local.py."""

import json
import os
import sys
from pathlib import Path

cfg = json.loads((Path(os.environ["LOCALAPPDATA"]) / "BBC Wine" / "local.json").read_text(encoding="utf-8"))
assert "@127.0.0.1:" in cfg["database_url"], "The local launcher only uses the local database."
os.environ.update(BBC_DATABASE_URL=cfg["database_url"], BBC_SECRET_KEY=cfg["secret_key"], BBC_LOCAL_AUTOLOGIN="1")
sys.path.insert(0, str(Path(__file__).parent / "app"))
os.chdir(Path(__file__).parent / "app")

import app as web  # noqa: E402

web.init_db()
web.app.run(host="127.0.0.1", port=int(cfg.get("port", 5110)), debug=False, use_reloader=False)
