"""The checks "Avvia Bank" and "Configura PC" run. Each returns a precise
problem in words, never a guess."""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

from .config import DATA_STORE_DIR, REPO_ROOT, TOOL_DIR, Config


# ---------------------------------------------------------------- Python and dependencies

def python_problems(cfg: Config) -> list[str]:
    want = cfg.environment["python_version"]
    have = f"{sys.version_info.major}.{sys.version_info.minor}"
    return [] if have == want else [f"Python {have} is running; the environment requires Python {want}."]


def locked_requirements(cfg: Config) -> dict[str, str]:
    lock = {}
    for line in (TOOL_DIR / cfg.environment["requirements_lock"]).read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            name, _, version = line.partition("==")
            lock[name.strip()] = version.strip()
    return lock


def dependency_problems(cfg: Config) -> list[str]:
    import importlib.metadata as md
    problems = []
    for name, version in locked_requirements(cfg).items():
        try:
            have = md.version(name)
        except md.PackageNotFoundError:
            problems.append(f"{name} is not installed (required {version}).")
            continue
        if have != version:
            problems.append(f"{name} {have} is installed; required {version}.")
    return problems


# ---------------------------------------------------------------- code version

def _code_files(cfg: Config) -> list[Path]:
    excludes = cfg.environment["code_excludes"]
    files = []
    for rel in cfg.environment["code_paths"]:
        path = REPO_ROOT / rel
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for p in candidates:
            posix = "/" + p.relative_to(REPO_ROOT).as_posix()
            if not any(x in posix or posix.endswith(x) for x in excludes):
                files.append(p)
    return files


def code_fingerprint(cfg: Config) -> str:
    """The content of the code the server runs (application, migrations, this
    tool), independent of git and of file dates: two PCs with the same files
    have the same fingerprint."""
    digest = hashlib.sha256()
    for p in _code_files(cfg):
        digest.update(p.relative_to(REPO_ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(p.read_bytes()).digest())
    return digest.hexdigest()


def git_head() -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=20)
        branch = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=20)
        return f"{branch.stdout.strip()}@{out.stdout.strip()}" if out.returncode == 0 else "git unavailable"
    except (OSError, subprocess.SubprocessError):
        return "git unavailable"


def code_version(cfg: Config, fingerprint: str | None = None) -> str:
    return f"{git_head()} · code {(fingerprint or code_fingerprint(cfg))[:10]}"


# ---------------------------------------------------------------- migrations

def migration_head() -> str:
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    alembic_cfg = AlembicConfig(str(DATA_STORE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(DATA_STORE_DIR / "migrations"))
    heads = ScriptDirectory.from_config(alembic_cfg).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"the code has {len(heads)} migration heads: {heads}")
    return heads[0]


def migration_is_ancestor(revision: str, head: str) -> bool:
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    alembic_cfg = AlembicConfig(str(DATA_STORE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(DATA_STORE_DIR / "migrations"))
    script = ScriptDirectory.from_config(alembic_cfg)
    return any(r.revision == revision for r in script.walk_revisions(base="base", head=head))


# ---------------------------------------------------------------- port

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def port_owner(port: int) -> str:
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=20).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
                return parts[4]
    except (OSError, subprocess.SubprocessError):
        pass
    return "?"


def process_command_line(pid: int | str) -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""


# ---------------------------------------------------------------- OneDrive

# Windows STORAGE_PROVIDER_STATE (propkey System.StorageProviderState).
SYNC_STATES = {0: "not managed by OneDrive", 1: "online only", 2: "in sync", 3: "in sync (always kept)",
               4: "waiting to upload", 5: "waiting to download", 6: "transferring", 7: "sync error",
               8: "sync warning", 9: "excluded from sync", 10: "not synced (incomplete / blocked)",
               11: "placeholder"}
IN_SYNC = {2, 3}


def onedrive_states(paths: list[Path]) -> dict[Path, int | None]:
    """OneDrive's own sync state of each file, as Explorer shows it."""
    if not paths:
        return {}
    script = ["$sh = New-Object -ComObject Shell.Application"]
    for p in paths:
        script.append(f"$ns = $sh.Namespace('{str(p.parent)}'); $it = $ns.ParseName('{p.name}');"
                      f" if ($it) {{ [string]$it.ExtendedProperty('System.StorageProviderState') }} else {{ 'MISSING' }}")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(script)], capture_output=True,
                         text=True, timeout=120)
    values = out.stdout.splitlines()
    result = {}
    for p, v in zip(paths, values + [""] * len(paths)):
        v = v.strip()
        result[p] = int(v) if v.isdigit() else None
    return result


def conflict_copies(cfg: Config) -> list[Path]:
    """OneDrive's conflict copies of the handoff control files: when two PCs
    wrote manifest.json / lease.json before syncing, OneDrive keeps both as
    "manifest-COMPUTERNAME.json". Snapshots have unique names and never clash."""
    if not cfg.handoff_dir.exists():
        return []
    return sorted(p for p in cfg.handoff_dir.iterdir()
                  if p.is_file() and re.match(r"(manifest|lease)-.+\.json$", p.name, re.IGNORECASE))


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
