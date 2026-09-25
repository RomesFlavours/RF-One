#!/usr/bin/env python
"""RF-One Web starts inside the layout its Docker image actually has.

Regression for TIPS_AWS_FINALIZATION_DEPLOY (2026-09-25): locally every
sibling folder of `03 Software/` is on disk, so an import that needs a folder
the image never copies passes every test and then crash-loops gunicorn on
App Runner. `tips_validation_routes.py` -> `tips.calculation_run_service` ->
the Clover connector -> `clover_explorer` did exactly that.

This test reads the COPY lines of the committed Dockerfile
(`03 Software/Infrastructure/deploy/rfone-web/Dockerfile`), rebuilds ONLY
those folders under a temporary `/app`-like root, and imports `app` there in
a fresh interpreter. A folder missing from the image fails here, not in
production. No network, no AWS; the import never touches the database.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[2]
DOCKERFILE = SOFTWARE_DIR / "Infrastructure" / "deploy" / "rfone-web" / "Dockerfile"
COPY_RE = re.compile(r'^COPY \["([^"]+)", "/app/([^"]+)"\]$', re.MULTILINE)


def main() -> int:
    copies = [(src, dst) for src, dst in COPY_RE.findall(DOCKERFILE.read_text()) if "/" not in src]
    workdir = re.search(r'^WORKDIR "/app/([^"]+)"$', DOCKERFILE.read_text(), re.MULTILINE).group(1)
    ok = True
    with tempfile.TemporaryDirectory(prefix="rfoneweb_image_") as root:
        for src, dst in copies:
            shutil.copytree(
                SOFTWARE_DIR / src, Path(root) / dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data", "tests"),
            )
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "RFONE_FLASK_SECRET_KEY")}
        env["RFONE_WEB_TEST_SECRET_KEY"] = "image-layout-test-secret"
        env["RFONE_DATABASE_URL"] = f"sqlite:///{Path(root, 'unused.db').as_posix()}"
        proc = subprocess.run(
            [sys.executable, "-c", "import app; print('ROUTES', len(list(app.app.url_map.iter_rules())))"],
            cwd=Path(root) / workdir, env=env, capture_output=True, text=True, timeout=300,
        )
        imported = proc.returncode == 0 and "ROUTES" in proc.stdout
        print(f"  {'PASS' if imported else 'FAIL'}  app.py imports in the image layout "
              f"({', '.join(d for _, d in copies)})")
        if not imported:
            ok = False
            print(proc.stderr[-3000:])
        has_tips = imported and "/tips/runs" in subprocess.run(
            [sys.executable, "-c", "import app; print([r.rule for r in app.app.url_map.iter_rules()])"],
            cwd=Path(root) / workdir, env=env, capture_output=True, text=True, timeout=300,
        ).stdout
        print(f"  {'PASS' if has_tips else 'FAIL'}  the Tips validation routes are registered")
        ok = ok and has_tips
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
