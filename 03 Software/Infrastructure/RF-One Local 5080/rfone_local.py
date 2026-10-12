"""RF-One Local 5080 — start, stop and check the whole RF-One web application
(Bank, Project Management and every other page of RF-One Web) on this PC,
from THIS worktree and on the database in use today
(`03 Software/RF-One Data Store/data/rfone.db`).

No adoption, no OneDrive synchronisation, no transfer between PCs, no
migration: those belong to the Bank Local Environment ("Avvia Bank"), which is
not used here. The server is the same one "Avvia Bank" runs
(`bank_local_env.serve`: local admin sign-in from this PC only, header bar
with PC, database, code and AI mode) with the same parameters.

The server is independent of whoever starts it (a double-click, a terminal, a
Claude Code session): it is started detached, directly on the base Python
interpreter. A venv's python.exe on Windows is only a redirector that runs the
interpreter inside a kill-on-close job; when the redirector was ended, the
server died with it, without a traceback (MINIPC-KSYR1, 2026-10-12).

    python rfone_local.py start   [--port 5080]
    python rfone_local.py stop    [--port 5080]
    python rfone_local.py status  [--port 5080]

Run it with this PC's Python, the one in
`Bank Local Environment/machines/<COMPUTERNAME>.json` (the .cmd files do).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BANK_ENV_DIR = HERE.parent / "Bank Local Environment"
sys.path.insert(0, str(BANK_ENV_DIR))

from bank_local_env import checks, config, dbtools  # noqa: E402  (read-only helpers)

DB = config.DATA_STORE_DIR / "data" / "rfone.db"
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Local 5080"
LOG = STATE_DIR / "server.log"
GENERATION_TEXT = "non adottato (database di lavoro della 5080, in uso sul posto)"
SERVE_MODULE = "bank_local_env.serve"


def say(text: str = "") -> None:
    print(text, flush=True)


def state_path(port: int) -> Path:
    return STATE_DIR / f"state-{port}.json"


def http_status(port: int, path: str) -> int | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return None


def owner(port: int) -> tuple[str | None, str]:
    """(pid, command line) of the process listening on `port`, if any."""
    if not checks.port_in_use(port):
        return None, ""
    pid = checks.port_owner(port)
    return pid, checks.process_command_line(pid) if pid else ""


def is_rfone_server(command: str, port: int) -> bool:
    return f"{SERVE_MODULE} {port}" in command


def server_command() -> tuple[str, dict]:
    """The base interpreter and the environment that makes it use this venv,
    exactly as the venv redirector would — without the redirector."""
    executable, extra = sys.executable, {}
    base = getattr(sys, "_base_executable", executable)
    if os.name == "nt" and base and Path(base).resolve() != Path(executable).resolve():
        extra["__PYVENV_LAUNCHER__"] = executable
        executable = base
    return executable, extra


def start(port: int) -> int:
    say(f"AVVIA RF-ONE — porta {port} — PC {config.computer_name()}")
    pid, command = owner(port)
    if pid:
        if is_rfone_server(command, port):
            say(f"  RF-One è già in esecuzione sulla porta {port} (processo {pid}). Nulla è stato avviato.")
            say(f"  Per riavviarlo: Ferma RF-One 5080, poi Avvia RF-One 5080.")
            return 0
        say(f"  RIFIUTATO: la porta {port} è occupata da un altro programma (processo {pid}): {command[:200]}")
        return 1

    if not DB.exists():
        say(f"  RIFIUTATO: il database non esiste: {DB}")
        return 1
    revision, head = dbtools.revision(DB), checks.migration_head()
    if revision != head:
        say(f"  RIFIUTATO: il database è alla revisione {revision}, il codice richiede {head}. "
            "Qui non si migra nulla: applicare la migrazione prima, con una copia di sicurezza.")
        return 1
    say(f"  ✓ Database {DB} (revisione {revision}, uguale al codice)")

    cfg = config.load("work")
    executable, extra = server_command()
    env = dict(os.environ)
    env.update(extra)
    env.update({
        "RFONE_DATABASE_URL": "sqlite:///" + DB.as_posix(),
        "RFONE_LOCAL_ENV_PC": config.computer_name(),
        "RFONE_LOCAL_ENV_KIND": cfg.kind,
        "RFONE_LOCAL_ENV_LABEL": cfg.label,
        "RFONE_LOCAL_ENV_DB": str(DB),
        "RFONE_LOCAL_ENV_GENERATION": GENERATION_TEXT,
        "RFONE_LOCAL_ENV_CODE": checks.code_version(cfg),
        "RFONE_BANK_AI_MODE": cfg.environment["ai_mode"],
        "RFONE_BANK_CLAUDE_CODE_CLI": cfg.environment.get("claude_code_cli", "off")
        if cfg.environment["ai_mode"].upper() == "SESSION" else "off",
        "PYTHONIOENCODING": "utf-8",
    })
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "a", encoding="utf-8")
    log.write(f"\n===== {time.strftime('%Y-%m-%dT%H:%M:%S')} start port {port}, database {DB}\n")
    log.flush()
    flags = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    proc = subprocess.Popen([executable, "-m", SERVE_MODULE, str(port)], cwd=str(BANK_ENV_DIR), env=env,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                            close_fds=True)
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            say(f"  RIFIUTATO: il server si è fermato subito (uscita {proc.returncode}); vedi {LOG}")
            return 1
        if http_status(port, "/bank") == 200:
            state_path(port).write_text(json.dumps({
                "pid": proc.pid, "port": port, "database": str(DB), "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "code": env["RFONE_LOCAL_ENV_CODE"], "python": executable,
            }, indent=2), encoding="utf-8")
            say(f"\nRF-ONE AVVIATO — http://127.0.0.1:{port}/   (processo {proc.pid}, log {LOG})")
            say(f"  Bank:               http://127.0.0.1:{port}/bank")
            say(f"  Project Management: http://127.0.0.1:{port}/projects")
            return 0
        time.sleep(1)
    proc.kill()
    say(f"  RIFIUTATO: il server non ha risposto entro 90 s; vedi {LOG}")
    return 1


def stop(port: int) -> int:
    say(f"FERMA RF-ONE — porta {port}")
    pid, command = owner(port)
    if not pid:
        say(f"  Nessun server sulla porta {port}: nulla da fermare.")
        state_path(port).unlink(missing_ok=True)
        return 0
    if not is_rfone_server(command, port):
        say(f"  RIFIUTATO: la porta {port} è di un altro programma (processo {pid}), non di RF-One: {command[:200]}")
        return 1
    # Only the RF-One server on this port. A venv redirector that started it
    # (older starts) ends on its own once its child has ended.
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
    for _ in range(20):
        if not checks.port_in_use(port):
            state_path(port).unlink(missing_ok=True)
            say(f"  ✓ Fermato il processo {pid}. La porta {port} è libera.")
            return 0
        time.sleep(0.5)
    say(f"  ATTENZIONE: la porta {port} risulta ancora occupata; controlla con Stato RF-One 5080.")
    return 1


def status(port: int) -> int:
    pid, command = owner(port)
    saved = json.loads(state_path(port).read_text(encoding="utf-8")) if state_path(port).exists() else None
    say(f"RF-ONE — porta {port} — PC {config.computer_name()}")
    say(f"  database:  {DB} (revisione {dbtools.revision(DB) if DB.exists() else 'assente'})")
    if not pid:
        say("  server:    non in esecuzione")
        return 0
    started_here = bool(saved and str(saved.get("pid")) == str(pid))
    say(f"  server:    processo {pid} — {'RF-One' if is_rfone_server(command, port) else 'NON RF-One'}"
        f"{', avviato da questo launcher il ' + saved['started_at'] if started_here else ''}")
    for path in ("/bank", "/projects"):
        say(f"  {path:16} HTTP {http_status(port, path)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rfone_local")
    parser.add_argument("command", choices=["start", "stop", "status"])
    parser.add_argument("--port", type=int, default=5080)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    return {"start": start, "stop": stop, "status": status}[args.command](args.port)


if __name__ == "__main__":
    sys.exit(main())
