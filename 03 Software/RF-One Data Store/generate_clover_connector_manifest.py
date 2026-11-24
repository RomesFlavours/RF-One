"""Regenerate `clover_connector_release.json` (CLOVER_ACQUISITION_ENGINE_001).

The worker image (`rfone-tips`, `03 Software/Infrastructure/deploy/rfone-tips/Dockerfile`) is built from
`git -c core.autocrlf=false archive` of the release tree and copies `RF-One Data Store` and
`Clover Data Explorer` whole. The start check (`clover_connector_release_check.py`) compares the SHA-256 of
the files' actual bytes in that image.

This script records exactly those bytes: it stages the current working tree into a TEMPORARY Git index
(the real index is untouched), writes a tree object, archives it with `core.autocrlf=false` exactly as the
image build does, and hashes each listed file as it appears in the archive. It adds the shared acquisition
engine to the list. `--extract DIR` also writes the archived `03 Software/RF-One Data Store` and
`03 Software/Clover Data Explorer` to DIR, so the start check can be run on the artifact bytes themselves.

No commit is created. Run it on the final release tree, then commit the manifest with the release.

Usage:
    python generate_clover_connector_manifest.py --release <release-name> [--extract DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent            # .../03 Software/RF-One Data Store
SOFTWARE = ROOT.parent                             # .../03 Software (the image build context)
MANIFEST = ROOT / "clover_connector_release.json"
ARTIFACT_DIRS = ("03 Software/RF-One Data Store", "03 Software/Clover Data Explorer")
ENGINE_FILES = (
    "RF-One Data Store/rfone_data_store/operational_acquisition.py",
    "RF-One Data Store/rfone_data_store/technical/connectors/clover/shared_cycle.py",
    "RF-One Data Store/test_operational_acquisition.py",
)
# The manifest cannot contain its own digest; every other listed file is verified.
NOT_LISTED = ("RF-One Data Store/clover_connector_release.json",)


def _git(*args: str, env: dict | None = None, binary: bool = False, cwd: Path = ROOT):
    out = subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)
    return out.stdout if binary else out.stdout.decode("utf-8").strip()


def build_artifact() -> tarfile.TarFile:
    """The release artifact as `git archive` produces it from the current working tree."""
    top = Path(_git("rev-parse", "--show-toplevel"))
    temp_dir = top.parent / "test-temp" if (top.parent / "test-temp").is_dir() else None
    fd, index = tempfile.mkstemp(prefix="clover-manifest-index-", dir=temp_dir)
    os.close(fd)
    os.remove(index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        _git("read-tree", "HEAD", env=env)
        _git("add", "-A", "--", *ARTIFACT_DIRS, env=env, cwd=top)
        tree = _git("write-tree", env=env)
    finally:
        try:
            os.remove(index)
        except OSError:
            pass
    data = _git("-c", "core.autocrlf=false", "archive", "--format=tar", tree, "--", *ARTIFACT_DIRS,
                binary=True, cwd=top)
    return tarfile.open(fileobj=io.BytesIO(data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", required=True)
    parser.add_argument("--extract", help="Also write the archived artifact directories here.")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = [f for f in list(manifest["files"]) + [f for f in ENGINE_FILES if f not in manifest["files"]]
             if f not in NOT_LISTED]
    artifact = build_artifact()
    digests = {}
    for name in files:
        member = artifact.extractfile("03 Software/" + name)
        if member is None:
            raise SystemExit(f"{name} is not in the artifact")
        digests[name] = hashlib.sha256(member.read()).hexdigest()
    manifest["release"] = args.release
    manifest["files"] = digests
    text = json.dumps(manifest, indent=2) + "\n"
    MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    print(f"{MANIFEST.name}: {len(files)} files, release {args.release}")
    if args.extract:
        target = Path(args.extract)
        artifact.extractall(target, filter="data") if hasattr(tarfile, "data_filter") else artifact.extractall(target)
        # The manifest just written is part of the release: place its committed (LF) bytes in the copy too.
        (target / "03 Software" / "RF-One Data Store" / MANIFEST.name).write_bytes(text.encode("utf-8"))
        print(f"artifact extracted to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
