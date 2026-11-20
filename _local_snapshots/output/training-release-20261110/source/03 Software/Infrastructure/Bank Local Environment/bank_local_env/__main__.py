"""bank_local_env — the local Bank environment, the same on every PC.

  python -m bank_local_env setup                 Configura PC
  python -m bank_local_env start  [--migrate] [--accept-code] [--ai SESSION|PROVIDER]   Avvia Bank
  python -m bank_local_env close  [--check] [--no-wait]                                Chiudi Bank / Cambia PC
  python -m bank_local_env status
  python -m bank_local_env adopt  --from DB --note TEXT [--replace-authority PC]
  python -m bank_local_env compare DB_A DB_B [...]
  python -m bank_local_env session pending | prompt ID | answer ID FILE [--model M]

Common options: --profile work|test (default work); --handoff-dir / --local-dir / --port override the
profile (used to verify the procedure on copies).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import checks, dbtools, handoff, session_ai
from .config import TOOL_DIR, Config, EnvError, computer_name, load, machine_file


def setup(args) -> int:
    """Configura PC: creates or checks this PC's machine file, installs the
    locked dependencies when they differ, and runs every check “Avvia Bank”
    needs that does not depend on the data."""
    print(f"CONFIGURA PC — {computer_name()}")
    path = machine_file()
    if not path.exists():
        detected = {"_comment": "Everything that differs on this PC. Keep it minimal.",
                    "computer_name": computer_name(), "python": sys.executable,
                    "onedrive": str(Path.home() / "OneDrive"), "verified": None}
        path.write_text(json.dumps(detected, indent=2), encoding="utf-8")
        print(f"  · machine file created with the detected values: {path} — commit it to the repository")
    cfg = load(args.profile, handoff_dir=args.handoff_dir, local_dir=args.local_dir, port=args.port)
    problems = []
    if Path(sys.executable).resolve() != Path(cfg.python).resolve():
        problems.append(f"this command runs with {sys.executable}, the machine file says {cfg.python}")
    problems += checks.python_problems(cfg)
    if not Path(cfg.machine["onedrive"]).exists():
        problems.append(f"the OneDrive folder {cfg.machine['onedrive']} does not exist")
    deps = checks.dependency_problems(cfg)
    if deps and not problems:
        print("  · installing the locked dependencies:\n    - " + "\n    - ".join(deps))
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                                 str(TOOL_DIR / cfg.environment["requirements_lock"])])
        if result.returncode != 0:
            problems.append("pip install of requirements.lock.txt failed")
        deps = checks.dependency_problems(cfg)
    problems += deps
    try:
        head = checks.migration_head()
    except Exception as exc:  # noqa: BLE001 — reported, not hidden
        problems.append(f"migrations cannot be read: {exc}")
        head = "?"
    if not cfg.handoff_dir.parent.exists():
        problems.append(f"{cfg.handoff_dir.parent} does not exist: OneDrive has not synced the AI-RF-ONE folder here")
    else:
        cfg.handoff_dir.mkdir(exist_ok=True)
    cfg.local_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = checks.code_fingerprint(cfg)
    print(f"  python:      {sys.executable} ({sys.version.split()[0]})")
    print(f"  onedrive:    {cfg.machine['onedrive']}")
    print(f"  handoff:     {cfg.handoff_dir}")
    print(f"  local dir:   {cfg.local_dir}")
    print(f"  code:        {checks.code_version(cfg, fingerprint)}")
    print(f"  migrations:  head {head}")
    print(f"  port:        {cfg.port} ({'IN USE by ' + checks.port_owner(cfg.port) if checks.port_in_use(cfg.port) else 'free'})")
    if problems:
        print("\nNOT CONFIGURED:\n  - " + "\n  - ".join(problems))
        return 1
    machine = json.loads(path.read_text(encoding="utf-8"))
    machine["verified"] = f"{handoff.now()} by Configura PC on {computer_name()}, code {fingerprint[:10]}"
    path.write_text(json.dumps(machine, indent=2), encoding="utf-8")
    print(f"\nPC CONFIGURATO — machine file marked verified ({path.name}).")
    return 0


def compare(args) -> int:
    paths = [Path(p) for p in args.databases]
    contents = {}
    for p in paths:
        print(f"{p.name}: revision {dbtools.revision(p)}, integrity {dbtools.integrity(p)}, SHA-256 {dbtools.sha256(p)[:16]}…")
        contents[p] = dbtools.content(p)
    labels = dict(dbtools.KEY_TABLES)
    for a, b in zip(paths, paths[1:]):
        diffs = [d for d in dbtools.diff(contents[a], contents[b]) if not d.equal and d.table != "alembic_version"]
        print(f"\n{a.name} → {b.name}: {'identical content' if not diffs else f'{len(diffs)} tables differ'}")
        for d in diffs:
            print(f"  {d.table:42} only first {d.only_a:5}  only second {d.only_b:5}  changed {d.changed:5}  "
                  f"({d.count_a} → {d.count_b}) {labels.get(d.table, '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bank_local_env")
    parser.add_argument("--profile", default="work")
    parser.add_argument("--handoff-dir")
    parser.add_argument("--local-dir")
    parser.add_argument("--port", type=int)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup")
    p = sub.add_parser("start")
    p.add_argument("--migrate", action="store_true")
    p.add_argument("--accept-code", action="store_true")
    p.add_argument("--ai", choices=["SESSION", "PROVIDER"])
    p = sub.add_parser("close")
    p.add_argument("--check", action="store_true", help="only verify the OneDrive delivery of the last close")
    p.add_argument("--no-wait", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("adopt")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--replace-authority")
    p = sub.add_parser("compare")
    p.add_argument("databases", nargs="+")
    p = sub.add_parser("session")
    p.add_argument("action", choices=["pending", "prompt", "answer"])
    p.add_argument("preview_id", nargs="?", type=int)
    p.add_argument("answer_file", nargs="?")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--db")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.command == "setup":
            return setup(args)
        if args.command == "compare":
            return compare(args)
        cfg: Config = load(args.profile, handoff_dir=args.handoff_dir, local_dir=args.local_dir, port=args.port)
        if args.command == "start":
            return handoff.start(cfg, accept_code=args.accept_code, migrate=args.migrate, ai_mode=args.ai)
        if args.command == "close":
            if args.check:
                manifest = checks.read_json(cfg.manifest_path) or {}
                targets = [cfg.handoff_dir / manifest["snapshot"]] if manifest else []
                return handoff.sync_report(cfg, targets + [cfg.manifest_path, cfg.lease_path], wait=not args.no_wait)
            return handoff.close(cfg, wait=not args.no_wait)
        if args.command == "status":
            return handoff.status(cfg)
        if args.command == "adopt":
            return handoff.adopt(cfg, Path(args.source), args.note, args.replace_authority)
        if args.command == "session":
            db = Path(args.db) if args.db else cfg.local_db
            if args.action == "pending":
                return session_ai.pending(cfg, db)
            if args.preview_id is None:
                parser.error("the preview id is required")
            if args.action == "prompt":
                return session_ai.prompt(cfg, db, args.preview_id)
            if not args.answer_file:
                parser.error("the answer file is required")
            return session_ai.answer(cfg, db, args.preview_id, Path(args.answer_file), args.model)
    except EnvError as exc:
        print(f"\nNON AVVIATO / NON ESEGUITO — {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
