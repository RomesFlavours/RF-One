"""Configuration of the local Bank environment: the shared environment.json,
the machine file of THIS PC, and the chosen profile (work / test).

Every path is derived here; nothing else in the environment hard-codes one.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent            # .../Infrastructure/Bank Local Environment
REPO_ROOT = TOOL_DIR.parent.parent.parent                    # the worktree root
WEB_DIR = REPO_ROOT / "03 Software" / "RF-One Web"
DATA_STORE_DIR = REPO_ROOT / "03 Software" / "RF-One Data Store"


class EnvError(Exception):
    """A precise reason why the environment cannot proceed."""


def computer_name() -> str:
    return (os.environ.get("COMPUTERNAME") or socket.gethostname()).upper()


@dataclass
class Config:
    profile: str
    label: str
    kind: str                 # WORK | TEST
    port: int
    handoff_dir: Path
    local_dir: Path
    machine: dict
    machine_file: Path
    environment: dict

    @property
    def snapshots_dir(self) -> Path:
        return self.handoff_dir / "snapshots"

    @property
    def manifest_path(self) -> Path:
        return self.handoff_dir / "manifest.json"

    @property
    def lease_path(self) -> Path:
        return self.handoff_dir / "lease.json"

    @property
    def local_db(self) -> Path:
        return self.local_dir / "rfone.db"

    @property
    def state_path(self) -> Path:
        return self.local_dir / "state.json"

    @property
    def previous_dir(self) -> Path:
        return self.local_dir / "previous"

    @property
    def log_path(self) -> Path:
        return self.local_dir / "server.log"

    @property
    def session_dir(self) -> Path:
        return self.local_dir / "session-interpretations"

    @property
    def python(self) -> str:
        return self.machine["python"]


def load_environment() -> dict:
    return json.loads((TOOL_DIR / "environment.json").read_text(encoding="utf-8"))


def machine_file(name: str | None = None) -> Path:
    return TOOL_DIR / "machines" / f"{name or computer_name()}.json"


def load(profile: str = "work", *, handoff_dir: str | None = None, local_dir: str | None = None,
         port: int | None = None) -> Config:
    environment = load_environment()
    if profile not in environment["profiles"]:
        raise EnvError(f"Unknown profile “{profile}”: expected one of {sorted(environment['profiles'])}.")
    path = machine_file()
    if not path.exists():
        raise EnvError(f"This PC ({computer_name()}) has no machine file: {path}. Run “Configura PC” first.")
    machine = json.loads(path.read_text(encoding="utf-8"))
    values = {"onedrive": machine["onedrive"], "localappdata": os.environ.get("LOCALAPPDATA", "")}
    p = environment["profiles"][profile]
    return Config(
        profile=profile, label=p["label"], kind=p["kind"], port=port or p["port"],
        handoff_dir=Path(handoff_dir or p["handoff_dir"].format(**values)),
        local_dir=Path(local_dir or p["local_dir"].format(**values)),
        machine=machine, machine_file=path, environment=environment)
