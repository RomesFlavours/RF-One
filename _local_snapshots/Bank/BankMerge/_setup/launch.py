"""BankMerge — start / stop / status of this independent prototype.

Everything belongs to this prototype alone:
  code      this folder (copy of the C-Bank page as served on 5080, 2026-11-04, uncommitted changes included)
  database  %LOCALAPPDATA%\\RF-One\\BankMerge\\rfone.db
  store     %LOCALAPPDATA%\\RF-One\\BankMerge\\C-Bank (exports)
  cache     %LOCALAPPDATA%\\RF-One\\BankMerge\\pycache
  log/state %LOCALAPPDATA%\\RF-One\\BankMerge\\server.log, state.json
  port      5104

No reconciliation, recalculation or AI call is started by this launcher or at server start
(CBANK_AUTO_RUN=0; the engine and the AI run only when the person presses their buttons).
The other Bank versions, their launchers and their databases are never read or written here,
except the read-only local AWS copy of other RF-One domains (RFONE_DOMAIN_DATA), as the 5080 page does.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

NAME = "BankMerge"
PORT = 5106
ROOT = Path(__file__).resolve().parents[1]
SOFTWARE = ROOT / "03 Software"
TOOL_DIR = SOFTWARE / "Infrastructure" / "Bank Local Environment"
DATA = Path(os.environ["LOCALAPPDATA"]) / "RF-One" / NAME
DB = DATA / "rfone.db"
STATE = DATA / "state.json"
LOG = DATA / "server.log"
URL = f"http://127.0.0.1:{PORT}/bank"
DOMAIN_DATA = Path(os.environ["LOCALAPPDATA"]) / "RF-One" / "AWS-Copy" / "20261025T130037Z" / "local-connection.json"


def port_in_use() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def environment() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RFONE_", "CBANK_", "ALEMBIC_"))}
    env.update({
        "RFONE_DATABASE_URL": "sqlite:///" + DB.as_posix(),
        "RFONE_LOCAL_ENV_PC": (os.environ.get("COMPUTERNAME") or socket.gethostname()).upper(),
        "RFONE_LOCAL_ENV_KIND": "WORK",
        "RFONE_LOCAL_ENV_LABEL": NAME,
        "RFONE_LOCAL_ENV_DB": str(DB),
        "RFONE_LOCAL_ENV_GENERATION": f"{NAME} (copia di prova)",
        "RFONE_LOCAL_ENV_CODE": NAME,
        "RFONE_BANK_AI_MODE": "SESSION",
        "RFONE_BANK_CLAUDE_CODE_CLI": "auto",
        "RFONE_UI_LANGUAGE": "it",
        "RFONE_BANK_GUIDED": "1",
        "RFONE_BANK_SINGLE_ENGINE": "1",
        "RFONE_BANK_CBANK_ROOT": str(SOFTWARE / "C-Bank Prototype"),
        "CBANK_BANK_DB": str(DB),
        "CBANK_STORE_DIR": str(DATA / "C-Bank"),
        "CBANK_BANK_CODE_ROOT": str(ROOT),
        "CBANK_WHO_WHY": "1",
        "CBANK_AUTO_RUN": "0",
        "RFONE_DOMAIN_DATA": str(DOMAIN_DATA) if DOMAIN_DATA.is_file() else "",
        "RFONE_WEB_TEST_SECRET_KEY": "bank-2026-11-04-local-only",
        "PYTHONPYCACHEPREFIX": str(DATA / "pycache"),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def start() -> int:
    if not DB.is_file():
        sys.exit(f"Database not found: {DB}")
    if port_in_use():
        print(f"{NAME} is already answering on port {PORT}: {URL}")
        return 0
    DATA.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "a", encoding="utf-8")
    log.write(f"\n===== {datetime.now().astimezone().isoformat()} start {NAME} port {PORT}\n")
    log.flush()
    flags = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    proc = subprocess.Popen([sys.executable, "-m", "bank_local_env.serve", str(PORT)], cwd=str(TOOL_DIR),
                            env=environment(), stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            sys.exit(f"The server stopped at once (exit {proc.returncode}); see {LOG}.")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/bank", timeout=5) as r:
                if r.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        proc.kill()
        sys.exit(f"No answer on port {PORT} within 90 s; see {LOG}.")
    STATE.write_text(json.dumps(dict(name=NAME, pid=proc.pid, port=PORT, url=URL, database=str(DB), code=str(ROOT),
                                     started_at=datetime.now().astimezone().isoformat(), status="RUNNING"),
                                indent=2), encoding="utf-8")
    print(f"{NAME} AVVIATO — {URL}  (pid {proc.pid}, database {DB})")
    return proc.pid


def stop() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}
    pid = state.get("pid")
    if not pid or not port_in_use():
        print(f"{NAME} is not running.")
        return
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                         capture_output=True, text=True).stdout
    if "bank_local_env.serve" not in out or str(PORT) not in out:
        sys.exit(f"Process {pid} is not the {NAME} server: nothing is stopped.")
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    state.update(status="STOPPED", stopped_at=datetime.now().astimezone().isoformat())
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"{NAME} fermato (pid {pid}).")


def open_edge() -> None:
    subprocess.Popen(["cmd", "/c", "start", "", "msedge", URL], creationflags=0x08000000)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "start":
        start()
        open_edge()
    elif action == "stop":
        stop()
    else:
        print(f"{NAME}: {'RUNNING' if port_in_use() else 'STOPPED'} — {URL}")
