"""Prova estesa lettura diretta — step 1: sample inventory and page renders.

Reads every PDF under AI-RF-ONE/Documents/Invoices/<Supplier>/, groups identical
files by SHA-256 (a duplicate is rendered once), and renders every page of each
distinct file with Poppler's pdftoppm:

  pagine/<supplier>_<sha12>_p<N>.png   300 dpi, for reading and for the PDFs
  campione.json                        files, duplicates, pages, SHA-256

No recognition service is called: the pages are only rasterised.
Run:  python render_pages.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[3] / "Documents" / "Invoices"          # AI-RF-ONE/Documents/Invoices
PAGES = HERE / "pagine"
POPPLER = Path.home() / ("AppData/Local/Microsoft/WinGet/Packages/"
                         "oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe/poppler-25.07.0/Library/bin")


def tool(name: str) -> str:
    found = shutil.which(name)
    return found or str(POPPLER / f"{name}.exe")


def main() -> None:
    PAGES.mkdir(exist_ok=True)
    by_hash: dict[str, dict] = {}
    for pdf in sorted(SOURCE.glob("*/*.pdf")):
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        entry = by_hash.setdefault(digest, {"sha256": digest, "supplier_folder": pdf.parent.name, "files": []})
        entry["files"].append(str(pdf.relative_to(SOURCE)).replace("\\", "/"))
    distinct = []
    for digest, entry in by_hash.items():
        first = SOURCE / entry["files"][0]
        info = subprocess.run([tool("pdfinfo"), str(first)], capture_output=True, text=True).stdout
        pages = int(next(line.split()[-1] for line in info.splitlines() if line.startswith("Pages:")))
        stem = f"{entry['supplier_folder'].replace(' ', '')}_{digest[:12]}"
        subprocess.run([tool("pdftoppm"), "-r", "300", "-png", str(first), str(PAGES / stem)], check=True)
        renders = sorted(PAGES.glob(f"{stem}-*.png"))
        names = []
        for n, path in enumerate(renders, start=1):
            target = PAGES / f"{stem}_p{n}.png"
            path.replace(target)
            names.append(target.name)
        entry.update(pages=pages, renders=names, duplicate_copies=len(entry["files"]) - 1)
        distinct.append(entry)
    summary = {
        "source": str(SOURCE),
        "files": sum(len(e["files"]) for e in distinct),
        "distinct_files": len(distinct),
        "duplicate_files": sum(e["duplicate_copies"] for e in distinct),
        "distinct_pages": sum(e["pages"] for e in distinct),
        "distinct": distinct,
    }
    (HERE / "campione.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "distinct"}, indent=2))
    for e in distinct:
        print(f"  {e['supplier_folder']:12} {e['sha256'][:12]} pages={e['pages']} copies={len(e['files'])} {e['files']}")


if __name__ == "__main__":
    main()
