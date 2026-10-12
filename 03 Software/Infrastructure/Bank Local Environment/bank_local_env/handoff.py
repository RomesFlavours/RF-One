"""One authoritative Bank database, handed between PCs through OneDrive.

The working database lives OUTSIDE OneDrive, on the local disk of the PC
that holds the work (`local_dir/rfone.db`): OneDrive never syncs an open
SQLite file. OneDrive carries only closed, consistent snapshots and two small
control files, in `handoff_dir`:

  snapshots/rfone_gNNNN_<PC>_<time>.db  one per "Chiudi Bank", never overwritten
  manifest.json   the authoritative generation: its snapshot, SHA-256, schema
                  revision, code fingerprint, who closed it and when
  lease.json      OPEN on <PC> while a PC works, CLOSED after "Chiudi Bank"

Rules that prevent overwriting newer work:
  * "Avvia Bank" refuses while the lease is OPEN on another PC;
  * a PC takes the snapshot only when its file is present AND its SHA-256 is
    the manifest's (OneDrive delivered it completely);
  * a local database changed since the generation it came from is never
    replaced by a newer generation (two lines of work: both kept, refused);
  * "Chiudi Bank" refuses when the manifest moved on since this PC opened;
  * OneDrive conflict copies of the control files stop everything.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import checks, dbtools
from .config import DATA_STORE_DIR, TOOL_DIR, Config, EnvError, computer_name

FORMAT = 1


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: dict) -> None:
    """Written whole, then renamed: a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def say(text: str = "") -> None:
    print(text, flush=True)


# ---------------------------------------------------------------- adopt

def adopt(cfg: Config, source: Path, note: str, replace: str | None = None) -> int:
    """Make `source` the authoritative database, generation 1 (or the next
    generation, with --replace-authority <PC NAME> when one exists)."""
    manifest = checks.read_json(cfg.manifest_path)
    if manifest is not None and replace != computer_name():
        raise EnvError(f"An authoritative database already exists (generation {manifest['generation']}, closed by "
                       f"{manifest['closed_by']} on {manifest['closed_at']}). Adopting another one would replace it: "
                       f"repeat with --replace-authority {computer_name()} only if that is what you decided.")
    source = Path(source)
    if not source.exists():
        raise EnvError(f"{source} does not exist.")
    result = dbtools.integrity(source)
    if result != "ok":
        raise EnvError(f"{source} fails the SQLite integrity check: {result}")
    generation = (manifest["generation"] + 1) if manifest else 1
    target = cfg.snapshots_dir / f"rfone_g{generation:04d}_{computer_name()}_{stamp()}.db"
    tmp = target.with_suffix(".db.tmp")
    dbtools.snapshot(source, tmp)
    os.replace(tmp, target)
    record = _manifest(cfg, target, generation, manifest, note=f"ADOPTED from {source}: {note}")
    write_json(cfg.manifest_path, record)
    write_json(cfg.lease_path, {"status": "CLOSED", "pc": computer_name(), "since": now(), "generation": generation})
    say(f"Authoritative database: generation {generation}, {target.name}")
    say(f"  SHA-256 {record['sha256']}  revision {record['revision']}  from {source}")
    return 0


def _manifest(cfg: Config, snapshot: Path, generation: int, previous: dict | None, *, note: str) -> dict:
    fingerprint = checks.code_fingerprint(cfg)
    return {
        "format": FORMAT, "generation": generation, "parent_generation": previous["generation"] if previous else None,
        "snapshot": f"snapshots/{snapshot.name}", "sha256": dbtools.sha256(snapshot), "size": snapshot.stat().st_size,
        "revision": dbtools.revision(snapshot), "code_fingerprint": fingerprint,
        "code_version": checks.code_version(cfg, fingerprint), "closed_by": computer_name(), "closed_at": now(),
        "profile": cfg.profile, "note": note,
    }


# ---------------------------------------------------------------- Avvia Bank

class Refused(EnvError):
    pass


def start(cfg: Config, *, accept_code: bool = False, migrate: bool = False, ai_mode: str | None = None) -> int:
    say(f"AVVIA BANK — {cfg.label} — PC {computer_name()}")
    problems = checks.python_problems(cfg) + checks.dependency_problems(cfg)
    if Path(sys.executable).resolve() != Path(cfg.python).resolve():
        problems.append(f"Running with {sys.executable}; this PC's machine file says {cfg.python}.")
    if problems:
        raise Refused("Python / dependencies do not match the environment:\n  - " + "\n  - ".join(problems)
                      + "\nRun “Configura PC”.")
    say("  ✓ Python and dependencies as in requirements.lock.txt")

    conflicts = checks.conflict_copies(cfg)
    if conflicts:
        raise Refused("OneDrive kept conflicting copies of the control files — two PCs wrote them before syncing:\n  "
                      + "\n  ".join(str(p) for p in conflicts) + "\nNothing is started. Resolve them first (see README).")
    manifest = checks.read_json(cfg.manifest_path)
    if manifest is None:
        raise Refused(f"No authoritative database has been delivered here ({cfg.manifest_path} missing). If OneDrive "
                      "is still downloading, wait; if this is the first time, adopt the authoritative database (README).")
    lease = checks.read_json(cfg.lease_path) or {}
    me = computer_name()
    if lease.get("status") == "OPEN" and lease.get("pc") != me:
        raise Refused(f"Bank is OPEN on {lease.get('pc')} since {lease.get('since')}: run “Chiudi Bank” there and wait "
                      "for the delivery. Nothing is started here.")
    say(f"  ✓ Authoritative database: generation {manifest['generation']}, closed by {manifest['closed_by']} "
        f"on {manifest['closed_at']}")

    state = checks.read_json(cfg.state_path)
    local_db = cfg.local_db
    take_snapshot = False
    if state and state.get("base_generation") == manifest["generation"] and local_db.exists():
        local_sha = dbtools.sha256(local_db)
        if local_sha == manifest["sha256"]:
            say("  ✓ The local database is exactly the authoritative one")
        elif lease.get("status") == "OPEN" and lease.get("pc") == me:
            say("  ! The local database has work NOT yet delivered (Bank was not closed on this PC): it is kept and used.")
        else:
            raise Refused("The local database changed after its last delivery, outside “Avvia Bank”. Nothing is "
                          f"replaced: {local_db} is kept. See README, “Two lines of work”.")
    elif state is None or state.get("base_generation", 0) < manifest["generation"] or not local_db.exists():
        if local_db.exists() and state and dbtools.sha256(local_db) != state.get("base_sha256"):
            raise Refused(f"This PC has work not delivered (local generation {state.get('base_generation')}, changed), "
                          f"and generation {manifest['generation']} was delivered from {manifest['closed_by']}: two "
                          f"lines of work. Both are kept ({local_db} and the snapshot); nothing is started. See README.")
        take_snapshot = True
    else:
        raise Refused(f"The manifest (generation {manifest['generation']}) is older than this PC's database "
                      f"(generation {state.get('base_generation')}): OneDrive has not delivered the latest manifest yet. "
                      "Wait for OneDrive and run “Avvia Bank” again.")

    if take_snapshot:
        snapshot = cfg.handoff_dir / manifest["snapshot"]
        if not snapshot.exists():
            raise Refused(f"The delivered snapshot is not on this PC yet ({snapshot.name}): OneDrive is still "
                          "downloading. Wait and run “Avvia Bank” again.")
        if dbtools.sha256(snapshot) != manifest["sha256"]:
            raise Refused(f"The snapshot {snapshot.name} is incomplete or different from the manifest (SHA-256 does not "
                          "match): OneDrive has not finished. Wait and run “Avvia Bank” again.")
        if local_db.exists():
            cfg.previous_dir.mkdir(parents=True, exist_ok=True)
            kept = cfg.previous_dir / f"rfone_local_{stamp()}.db"
            shutil.move(str(local_db), kept)
            say(f"  · previous local database kept as {kept.name}")
        cfg.local_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot, local_db)
        if dbtools.sha256(local_db) != manifest["sha256"]:
            raise Refused("The copy of the snapshot on the local disk does not match its SHA-256. Nothing is started.")
        state = {"base_generation": manifest["generation"], "base_sha256": manifest["sha256"]}
        write_json(cfg.state_path, state)
        say(f"  ✓ Generation {manifest['generation']} taken from OneDrive (SHA-256 verified)")

    fingerprint = checks.code_fingerprint(cfg)
    if fingerprint != manifest["code_fingerprint"]:
        message = (f"The code here (code {fingerprint[:10]}) is not the code generation {manifest['generation']} was "
                   f"closed with on {manifest['closed_by']} (code {manifest['code_fingerprint'][:10]}).")
        if not accept_code:
            raise Refused(message + " If OneDrive is still syncing the code, wait and retry; if the code was changed "
                          "on purpose, run “Avvia Bank” with --accept-code.")
        say(f"  ! {message} Accepted (--accept-code).")
    else:
        say(f"  ✓ Code identical to the closing one ({checks.code_version(cfg, fingerprint)})")

    revision, head = dbtools.revision(local_db), checks.migration_head()
    if revision != head:
        if revision and checks.migration_is_ancestor(revision, head):
            if not migrate:
                raise Refused(f"The database is at revision {revision}; the code needs {head}. Run “Avvia Bank” with "
                              "--migrate (a copy is kept first).")
            _migrate(cfg, local_db)
            say(f"  ✓ Migrated {revision} → {head} (copy kept in {cfg.previous_dir.name})")
        else:
            raise Refused(f"The database is at revision {revision}, which the code (head {head}) does not know: the "
                          "data is newer than the code. Nothing is started.")
    else:
        say(f"  ✓ Migrations: database at the code's head ({head})")

    if checks.port_in_use(cfg.port):
        pid = checks.port_owner(cfg.port)
        raise Refused(f"Port {cfg.port} is already in use by process {pid}: {checks.process_command_line(pid)[:200]}. "
                      "Nothing is started.")
    say(f"  ✓ Port {cfg.port} free")

    mode = (ai_mode or cfg.environment["ai_mode"]).upper()
    previous_lease = lease
    write_json(cfg.lease_path, {"status": "OPEN", "pc": me, "since": now(), "generation": manifest["generation"]})
    try:
        pid = _spawn(cfg, local_db, manifest, fingerprint, mode)
    except Exception:
        write_json(cfg.lease_path, previous_lease or {"status": "CLOSED", "pc": me, "since": now(),
                                                      "generation": manifest["generation"]})
        raise
    state.update(pid=pid, port=cfg.port, opened_at=now(), status="RUNNING", code_fingerprint=fingerprint, ai_mode=mode)
    write_json(cfg.state_path, state)
    say(f"\nBANK AVVIATO — http://127.0.0.1:{cfg.port}/bank   (pid {pid}, database {local_db}, AI {mode})")
    return 0


def _migrate(cfg: Config, db: Path) -> None:
    cfg.previous_dir.mkdir(parents=True, exist_ok=True)
    dbtools.snapshot(db, cfg.previous_dir / f"rfone_before_migration_{stamp()}.db")
    code = ("import sys; sys.path.insert(0, r'%s'); from rfone_data_store.database import run_migrations_to_head; "
            "run_migrations_to_head(r'sqlite:///%s')" % (DATA_STORE_DIR, db.as_posix()))
    result = subprocess.run([sys.executable, "-c", code], cwd=str(DATA_STORE_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        raise Refused("The migration failed; the copy taken before it is in " + str(cfg.previous_dir) + ":\n"
                      + result.stderr[-2000:])


def _spawn(cfg: Config, db: Path, manifest: dict, fingerprint: str, mode: str) -> int:
    env = dict(os.environ)
    env.update({
        "RFONE_DATABASE_URL": "sqlite:///" + db.as_posix(),
        "RFONE_LOCAL_ENV_PC": computer_name(),
        "RFONE_LOCAL_ENV_KIND": cfg.kind,
        "RFONE_LOCAL_ENV_LABEL": cfg.label,
        "RFONE_LOCAL_ENV_DB": str(db),
        "RFONE_LOCAL_ENV_GENERATION": f"{manifest['generation']} ({manifest['closed_by']}, {manifest['closed_at']})",
        "RFONE_LOCAL_ENV_CODE": checks.code_version(cfg, fingerprint),
        "RFONE_BANK_AI_MODE": mode,
        # BANK_AI_RULES_012 — SESSION mode: the Preview asks the local Claude Code CLI itself.
        "RFONE_BANK_CLAUDE_CODE_CLI": cfg.environment.get("claude_code_cli", "off") if mode == "SESSION" else "off",
        "PYTHONIOENCODING": "utf-8",
    })
    cfg.local_dir.mkdir(parents=True, exist_ok=True)
    log = open(cfg.log_path, "a", encoding="utf-8")
    log.write(f"\n===== {now()} start generation {manifest['generation']} port {cfg.port}\n")
    log.flush()
    flags = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    # A venv's python.exe on Windows is only a redirector: it starts the base
    # interpreter inside a kill-on-close job and waits for it, so when the
    # redirector is ended the server dies with it, without any traceback
    # (seen on MINIPC-KSYR1, 2026-10-12, with Avvia Bank started from a
    # Claude Code session). Start the base interpreter directly and tell it
    # which venv to use, exactly as the redirector does: the server then
    # depends on no process but itself.
    executable = sys.executable
    base = getattr(sys, "_base_executable", executable)
    if os.name == "nt" and base and Path(base).resolve() != Path(executable).resolve():
        env["__PYVENV_LAUNCHER__"] = executable
        executable = base
    proc = subprocess.Popen([executable, "-m", "bank_local_env.serve", str(cfg.port)], cwd=str(TOOL_DIR), env=env,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise Refused(f"The server stopped at once (exit {proc.returncode}); see {cfg.log_path}.")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/bank", timeout=5) as response:
                if response.status == 200:
                    return proc.pid
        except OSError:
            time.sleep(1)
    proc.kill()
    raise Refused(f"The server did not answer on port {cfg.port} within 60 s; see {cfg.log_path}.")


# ---------------------------------------------------------------- Chiudi Bank / Cambia PC

def stop_server(cfg: Config, state: dict | None) -> None:
    pid = (state or {}).get("pid")
    if pid and checks.port_in_use(cfg.port):
        owner = checks.port_owner(cfg.port)
        command = checks.process_command_line(pid)
        if str(owner) != str(pid) or "bank_local_env.serve" not in command:
            raise Refused(f"Port {cfg.port} is held by process {owner}, not by the Bank server this PC started "
                          f"(pid {pid}). Nothing is stopped.")
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        for _ in range(30):
            if not checks.port_in_use(cfg.port):
                break
            time.sleep(1)
        else:
            raise Refused(f"The server (pid {pid}) did not stop.")
        say(f"  ✓ Server stopped (pid {pid})")
    elif checks.port_in_use(cfg.port):
        raise Refused(f"Port {cfg.port} is in use by process {checks.port_owner(cfg.port)}, which this PC's Bank did not "
                      "start. Nothing is stopped.")
    else:
        say("  ✓ No server running")


def close(cfg: Config, *, wait: bool = True) -> int:
    say(f"CHIUDI BANK / CAMBIA PC — {cfg.label} — PC {computer_name()}")
    me = computer_name()
    state = checks.read_json(cfg.state_path)
    if state is None or not cfg.local_db.exists():
        raise Refused("This PC has no local Bank database: there is nothing to close.")
    stop_server(cfg, state)
    state.update(status="STOPPED", pid=None)
    write_json(cfg.state_path, state)

    con = sqlite3.connect(cfg.local_db, timeout=5)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.rollback()
    except sqlite3.OperationalError as exc:
        raise Refused(f"The local database is still in use ({exc}). Nothing is delivered.") from exc
    finally:
        con.close()
    result = dbtools.integrity(cfg.local_db)
    if result != "ok":
        raise Refused(f"The local database fails the integrity check: {result}. Nothing is delivered.")
    say("  ✓ Local database closed and intact")

    conflicts = checks.conflict_copies(cfg)
    if conflicts:
        raise Refused("OneDrive conflict copies of the control files exist; nothing is delivered:\n  "
                      + "\n  ".join(str(p) for p in conflicts))
    manifest = checks.read_json(cfg.manifest_path)
    lease = checks.read_json(cfg.lease_path) or {}
    if lease.get("status") == "OPEN" and lease.get("pc") != me:
        raise Refused(f"The lease says Bank is OPEN on {lease.get('pc')} since {lease.get('since')}: two PCs opened the "
                      f"same generation. Nothing is delivered; {cfg.local_db} is kept. See README, “Two lines of work”.")
    if manifest is None or manifest["generation"] != state.get("base_generation"):
        raise Refused(f"The authoritative generation is {manifest and manifest['generation']}, but this PC worked on "
                      f"generation {state.get('base_generation')}: another PC delivered in the meantime. Nothing is "
                      f"overwritten; {cfg.local_db} is kept. See README, “Two lines of work”.")
    local_sha = dbtools.sha256(cfg.local_db)
    if local_sha == manifest["sha256"]:
        fingerprint = checks.code_fingerprint(cfg)
        if fingerprint != manifest["code_fingerprint"]:
            # Same data, newer code: the other PC must wait for THIS code.
            manifest.update(code_fingerprint=fingerprint, code_version=checks.code_version(cfg, fingerprint),
                            note=f"{manifest.get('note', '')} · code updated by {me} on {now()}".strip(" ·"))
            write_json(cfg.manifest_path, manifest)
            say(f"  ✓ Data unchanged since generation {manifest['generation']}; the code changed: manifest updated "
                f"to code {fingerprint[:10]}.")
        else:
            say(f"  ✓ No change since generation {manifest['generation']}: nothing new to deliver.")
        write_json(cfg.lease_path, {"status": "CLOSED", "pc": me, "since": now(), "generation": manifest["generation"]})
        targets = [cfg.handoff_dir / manifest["snapshot"]]
    else:
        generation = manifest["generation"] + 1
        snapshot = cfg.snapshots_dir / f"rfone_g{generation:04d}_{me}_{stamp()}.db"
        tmp = snapshot.with_suffix(".db.tmp")
        dbtools.snapshot(cfg.local_db, tmp)
        if dbtools.integrity(tmp) != "ok":
            raise Refused("The snapshot fails the integrity check; nothing is delivered.")
        os.replace(tmp, snapshot)
        record = _manifest(cfg, snapshot, generation, manifest, note="Chiudi Bank")
        # The local database becomes byte-identical to what is delivered.
        shutil.copyfile(snapshot, cfg.local_db)
        write_json(cfg.manifest_path, record)
        write_json(cfg.lease_path, {"status": "CLOSED", "pc": me, "since": now(), "generation": generation})
        state.update(base_generation=generation, base_sha256=record["sha256"], closed_at=now())
        write_json(cfg.state_path, state)
        say(f"  ✓ FILE PREPARATO: generation {generation} — {snapshot.name} (SHA-256 {record['sha256'][:16]}…)")
        targets = [snapshot]
    targets += [cfg.manifest_path, cfg.lease_path]
    return sync_report(cfg, targets, wait=wait)


def sync_report(cfg: Config, targets: list[Path], *, wait: bool) -> int:
    """Prepared is not delivered: OneDrive's own state of each file says when
    the upload is complete. The definitive proof is “Avvia Bank” on the other
    PC, which verifies the SHA-256."""
    deadline = time.time() + (cfg.environment["sync_wait_seconds"] if wait else 0)
    if wait:
        say("  · waiting for OneDrive to pick the files up…")
        time.sleep(15)
    in_sync_readings = 0
    while True:
        states = checks.onedrive_states(targets)
        if all(v == 0 or v is None for v in states.values()):
            say("  ! These files are not managed by OneDrive (" + str(cfg.handoff_dir) + "): no delivery happens.")
            return 3
        # Two consecutive "in sync" readings, 10 s apart: a file just written
        # is not trusted on a single reading.
        in_sync_readings = in_sync_readings + 1 if all(v in checks.IN_SYNC for v in states.values()) else 0
        if in_sync_readings >= (2 if wait else 1):
            say("  ✓ SINCRONIZZAZIONE COMPLETATA secondo OneDrive: " + ", ".join(p.name for p in targets))
            say("    You can switch PC. The other PC verifies the SHA-256 when “Avvia Bank” takes it.")
            return 0
        if time.time() >= deadline:
            break
        time.sleep(10)
    say("  ✗ SINCRONIZZAZIONE NON ANCORA CONFERMATA — do not switch PC yet:")
    for p, v in states.items():
        say(f"      {p.name}: {checks.SYNC_STATES.get(v, v)}")
    say("    Check OneDrive, then run “Chiudi Bank” with --check to verify again.")
    return 2


# ---------------------------------------------------------------- status

def status(cfg: Config) -> int:
    manifest = checks.read_json(cfg.manifest_path)
    lease = checks.read_json(cfg.lease_path)
    state = checks.read_json(cfg.state_path)
    say(f"{cfg.label} — PC {computer_name()} — port {cfg.port}")
    say(f"  handoff (OneDrive): {cfg.handoff_dir}")
    say(f"  local database:     {cfg.local_db} ({'present' if cfg.local_db.exists() else 'absent'})")
    say(f"  manifest: {json.dumps(manifest, ensure_ascii=False) if manifest else 'none'}")
    say(f"  lease:    {json.dumps(lease, ensure_ascii=False) if lease else 'none'}")
    say(f"  local:    {json.dumps(state, ensure_ascii=False) if state else 'none'}")
    say(f"  server:   {'running' if checks.port_in_use(cfg.port) else 'not running'} on {cfg.port}")
    conflicts = checks.conflict_copies(cfg)
    say(f"  conflict copies: {', '.join(p.name for p in conflicts) if conflicts else 'none'}")
    if manifest:
        snapshot = cfg.handoff_dir / manifest["snapshot"]
        states = checks.onedrive_states([snapshot, cfg.manifest_path] + ([cfg.lease_path] if lease else []))
        for p, v in states.items():
            say(f"  OneDrive {p.name}: {checks.SYNC_STATES.get(v, v)}")
    return 0
