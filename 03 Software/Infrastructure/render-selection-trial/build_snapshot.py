"""Package source by allowlist. Never copy databases, uploads, .env or credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FOLDERS = ("Selection", "RF-One Data Store", "RF-One Web", "Training", "Shared UI", "Clover Data Explorer")
SUFFIXES = {".py", ".html", ".css", ".js", ".svg", ".png", ".ico", ".woff", ".woff2"}
EXCLUDED = {"data", "uploads", "__pycache__", "venv", ".venv", "node_modules", "previews"}


def build(destination: Path):
    destination = destination.resolve()
    if destination.exists():
        raise RuntimeError("Destination must be new; snapshots are never overwritten")
    destination.mkdir(parents=True)
    for folder in FOLDERS:
        source = REPO / "03 Software" / folder
        for path in source.rglob("*"):
            rel = path.relative_to(source)
            if not path.is_file() or any(part in EXCLUDED for part in rel.parts):
                continue
            allowed = path.suffix.lower() in SUFFIXES or path.name in {"requirements.txt", "alembic.ini"}
            allowed |= path.suffix == ".csv" and "migration_data" in rel.parts
            if not allowed or path.name in {"configure_smtp.py", "smtp_local_config.py", "local_server.py"}:
                continue
            target = destination / "03 Software" / folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    # Existing historical migration exceeds PostgreSQL's 63-character name limit.
    # Adjust only the disposable snapshot; never rewrite production migration history.
    migration = destination / "03 Software/RF-One Data Store/migrations/versions/b3f9d2c6e4a1_add_invoice_intake_data_model.py"
    source = migration.read_text(encoding="utf-8-sig")
    old = "ck_purchased_line_derived_values_product_card_requires_packaging"
    if old not in source:
        raise RuntimeError("Historical migration changed; review the PostgreSQL adaptation")
    migration.write_text(source.replace(old, "ck_pldv_product_card_packaging"), encoding="utf-8")
    for name in ("trial_wsgi.py", "requirements.txt", "render.yaml", "README.md", "test_trial_wsgi.py"):
        shutil.copyfile(HERE / name, destination / name)
    (destination / ".gitignore").write_text(".env\ntrial-uploads/\n*.db\n__pycache__/\n", encoding="utf-8")
    for path in destination.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".html", ".css", ".js", ".svg", ".ini", ".txt", ".csv", ".yaml", ".md"}:
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    files = {str(p.relative_to(destination)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob("*")) if p.is_file()}
    manifest = {"source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                "source": "allowlisted working-tree snapshot; includes uncommitted Selection integration",
                "adaptations": ["shorten historical PostgreSQL constraint in disposable snapshot"], "sha256": files}
    (destination / "snapshot-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Snapshot: {destination}; {len(files)} source files; no operational data")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    build(parser.parse_args().destination)
