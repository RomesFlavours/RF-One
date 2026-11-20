"""Build-time check: this tree's Alembic chain is compatible with the shared AWS database.

Run by every service image build (the Dockerfiles under
`03 Software/Infrastructure/deploy/`), before anything is pushed:

    python "RF-One Data Store/check_migration_chain.py" [--aws-revision REV]

It refuses (exit 1) when:
- two migration files declare the same revision id;
- a migration names a parent that is not in the tree;
- the tree has more than one head (an unmerged fork of the shared chain);
- the revision applied on AWS is not the head or one of its ancestors, i.e. the
  service would be built without a migration that is already in the database.

The AWS revision comes from `--aws-revision`, else the RFONE_AWS_SCHEMA_REVISION
environment variable (the buildspecs pass the deployment bucket's copy), else
`migrations/aws_applied_revision.json` in this tree. Standard library only: it
reads the migration files as text and never connects to a database.
See MIGRATIONS.md.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS_DIR = HERE / "migrations" / "versions"
REGISTRY = HERE / "migrations" / "aws_applied_revision.json"
ENV_VAR = "RFONE_AWS_SCHEMA_REVISION"


def _declared(path: Path) -> dict:
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for target in targets:
            if isinstance(target, ast.Name) and target.id in ("revision", "down_revision") and node.value is not None:
                values[target.id] = ast.literal_eval(node.value)
    return values


def load_graph(versions_dir: Path = VERSIONS_DIR) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    """Return ({revision: parents}, problems) for the migration files in `versions_dir`."""
    parents: dict[str, tuple[str, ...]] = {}
    files: dict[str, str] = {}
    problems = []
    for path in sorted(versions_dir.glob("*.py")):
        declared = _declared(path)
        if "revision" not in declared:
            continue
        revision, down = declared["revision"], declared.get("down_revision")
        if revision in parents:
            problems.append(f"revision {revision} is declared by both {files[revision]} and {path.name}")
        parents[revision] = tuple(down) if isinstance(down, (list, tuple)) else ((down,) if down else ())
        files[revision] = path.name
    for revision, ups in parents.items():
        problems += [f"{files[revision]} names missing parent {up}" for up in ups if up not in parents]
    return parents, problems


def ancestors(parents: dict[str, tuple[str, ...]], revision: str) -> set[str]:
    seen, stack = set(), [revision]
    while stack:
        current = stack.pop()
        if current not in seen and current in parents:
            seen.add(current)
            stack.extend(parents[current])
    return seen


def aws_revision(explicit: str | None = None) -> tuple[str, str]:
    """Return (revision, where it came from)."""
    if explicit:
        return explicit, "--aws-revision"
    if os.environ.get(ENV_VAR, "").strip():
        return os.environ[ENV_VAR].strip(), ENV_VAR
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["revision"], REGISTRY.name


def check(versions_dir: Path, required: str) -> tuple[list[str], list[str]]:
    """Return (heads, problems) for a tree that must contain revision `required`."""
    parents, problems = load_graph(versions_dir)
    children = {up for ups in parents.values() for up in ups}
    heads = sorted(r for r in parents if r not in children)
    if len(heads) != 1:
        problems.append(f"the chain must have exactly one head, found {len(heads)}: {', '.join(heads) or 'none'}")
    if required not in parents:
        problems.append(f"AWS revision {required} is not in this tree: add the migration file already applied on AWS")
    elif len(heads) == 1 and required not in ancestors(parents, heads[0]):
        problems.append(f"AWS revision {required} is not an ancestor of head {heads[0]}")
    return heads, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aws-revision", help="revision applied on AWS (overrides env and registry)")
    parser.add_argument("--versions-dir", type=Path, default=VERSIONS_DIR)
    args = parser.parse_args(argv)
    required, source = aws_revision(args.aws_revision)
    heads, problems = check(args.versions_dir, required)
    if problems:
        for problem in problems:
            print(f"MIGRATION CHAIN REFUSED: {problem}", file=sys.stderr)
        return 1
    print(f"MIGRATION CHAIN OK head={heads[0]} contains AWS revision {required} (from {source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
