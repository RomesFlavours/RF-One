#!/usr/bin/env python
"""How Works release check (UI_HOW_WORKS_001, `How Works Standard.md` in this folder).

    python check_how_works.py [--app NAME ...] [--rev COMMIT] [--since COMMIT] [--report]

Without --rev it reads the working tree; with --rev it reads that commit only (what a release builds).
With --since it also checks that every functional commit after COMMIT changed the Help of what it changed.
Exit code 0: no error. Exit code 1: release error. Standard library and Git only.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                   # repository root
REGISTRY = "03 Software/Shared UI/how_works_registry.json"
LINK_MARKER = "data-how-works"
COMPONENT = "03 Software/Shared UI/help/_how_works.html"  # the one help component; each app keeps an identical copy
SECTION_SET = re.compile(r"{%-?\s*set\s+help_section\s*=")
MIN_HELP_TEXT = 300                                      # visible characters: a real explanation, not a stub
TECHNICAL = re.compile(r"^How-Works:\s*technical\b", re.I | re.M)
REFERENCE_TAG = re.compile(r"{%-?\s*(?:extends|include|import|from)\s+(.*?)-?%}", re.S)
QUOTED = re.compile(r"""["']([^"']+\.html)["']""")
FUNCTIONAL_SUFFIXES = (".py", ".html", ".js", ".css")


class Source:
    """The repository files, from the working tree or from one commit."""

    def __init__(self, root: Path, rev: str | None):
        self.root, self.rev = root, rev
        self._files: set[str] | None = None

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True,
                              encoding="utf-8", errors="replace").stdout

    def files(self) -> set[str]:
        if self._files is None:
            if self.rev:
                self._files = set(self.git("ls-tree", "-r", "--name-only", self.rev, "--", "03 Software").splitlines())
            else:
                base = self.root / "03 Software"
                self._files = {p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file()}
        return self._files

    def exists(self, path: str) -> bool:
        return path in self.files()

    def read(self, path: str) -> str:
        if self.rev:
            return self.git("show", f"{self.rev}:{path}")
        return (self.root / path).read_text(encoding="utf-8", errors="replace")


def is_page(text: str) -> bool:
    """A page is rendered on its own: it extends a layout or is a whole HTML document. Anything else is a fragment."""
    return bool(re.search(r"{%-?\s*extends\s", text)) or bool(re.search(r"<html[\s>]", text, re.I))


def page_templates(src: Source, templates: str) -> dict[str, str]:
    """Template name (relative to the templates folder) -> text, for the page templates of one app."""
    prefix = templates.rstrip("/") + "/"
    pages = {}
    for path in sorted(src.files()):
        if not path.startswith(prefix) or not path.endswith(".html"):
            continue
        name = path[len(prefix):]
        if posixpath.basename(name).startswith("_"):
            continue
        text = src.read(path)
        if is_page(text):
            pages[name] = text
    return pages


def references(text: str) -> list[str]:
    """Templates named by extends/include/import/from tags, every branch of a conditional extends included."""
    return [name for tag in REFERENCE_TAG.findall(text) for name in QUOTED.findall(tag)]


def targets(entry) -> list[str]:
    """A registry `pages` entry: one target, or a list when one template renders several tabs."""
    return [entry] if isinstance(entry, str) else list(entry)


def chain_text(src: Source, folders: list[str], name: str, seen: set[str] | None = None) -> str:
    """The page plus every template it extends, includes or imports (layouts, components), searched in
    the app's own templates first and then in the layouts it borrows (`layout_templates`)."""
    seen = seen if seen is not None else set()
    if name in seen:
        return ""
    seen.add(name)
    path = next((f"{folder}/{name}" for folder in folders if src.exists(f"{folder}/{name}")), None)
    if not path:
        return ""
    text = src.read(path)
    return text + "".join(chain_text(src, folders, ref, seen) for ref in references(text))


def has_link(src: Source, templates, name: str) -> bool:
    """The page or a template it extends, includes or imports carries the How Works marker."""
    folders = [templates] if isinstance(templates, str) else list(templates)
    return LINK_MARKER in chain_text(src, folders, name)


def visible_text(html: str) -> str:
    """What a reader actually sees of a help section: no template tags, comments, scripts or markup."""
    text = re.sub(r"{#.*?#}|{%.*?%}|{{.*?}}", " ", html, flags=re.S)
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def check_help_section(src: Source, templates: str, app_name: str, name: str, guide: str) -> list[str]:
    """A section shown in the page's own help modal (`help/<section>.html`): the page declares exactly
    this section, and the section really explains something."""
    errors = []
    section = posixpath.splitext(guide[len("help/"):])[0]
    page = f"{templates}/{name}"
    text = src.read(page) if src.exists(page) else ""
    if not SECTION_SET.search(text) or not re.search(rf"""["']{re.escape(section)}["']""", text):
        errors.append(f'{app_name}: {name} does not declare {{% set help_section = "{section}" %}}')
    if len(visible_text(src.read(f"{templates}/{guide}"))) < MIN_HELP_TEXT:
        errors.append(f"{app_name}: {name} -> {guide}: the help section is too short to explain the page")
    return errors


def check_tree(src: Source, apps: dict, report: bool) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    canonical = src.read(COMPONENT) if src.exists(COMPONENT) else None
    for app_name, app in apps.items():
        templates = app["templates"]
        folders = [templates] + list(app.get("layout_templates", []))
        pages = page_templates(src, templates)
        copy = f"{templates}/_how_works.html"
        if canonical is not None and src.exists(copy) and src.read(copy) != canonical:
            errors.append(f"{app_name}: {copy} differs from the one help component {COMPONENT}: copy it again")
        listed = {"pages": app.get("pages", {}), "not_operational": app.get("not_operational", {}),
                  "help_missing": app.get("help_missing", {})}
        for name in pages:
            where = [k for k, v in listed.items() if name in v]
            if not where:
                errors.append(f"{app_name}: page {name} has no How Works (not in the registry: new page?)")
            elif len(where) > 1:
                errors.append(f"{app_name}: page {name} is in more than one registry list: {where}")
        for kind, entries in listed.items():
            for name in entries:
                if not src.exists(f"{templates}/{name}"):
                    errors.append(f"{app_name}: registry {kind} entry {name} does not exist")
        for name, entry in listed["pages"].items():
            for target in targets(entry):
                guide, _, anchor = target.partition("#")
                if not anchor:
                    errors.append(f"{app_name}: {name} -> {target}: the target opens the top of the guide, not a section")
                if not src.exists(f"{templates}/{guide}"):
                    errors.append(f"{app_name}: {name} -> {target}: guide {guide} does not exist")
                elif anchor and not re.search(rf"""\bid=["']{re.escape(anchor)}["']""", src.read(f"{templates}/{guide}")):
                    errors.append(f"{app_name}: {name} -> {target}: the guide has no section id \"{anchor}\"")
                elif guide.startswith("help/"):
                    errors += check_help_section(src, templates, app_name, name, guide)
            if src.exists(f"{templates}/{name}") and not has_link(src, folders, name):
                errors.append(f"{app_name}: {name} shows no How Works link ({LINK_MARKER})")
        if report:
            for name, reason in listed["help_missing"].items():
                warnings.append(f"{app_name}: {name} still without page-specific Help — {reason}")
    return errors, warnings


def functional(app: dict, path: str) -> bool:
    root = app["root"].rstrip("/") + "/"
    if not path.startswith(root) or not path.endswith(FUNCTIONAL_SUFFIXES):
        return False
    rel = path[len(root):]
    base = posixpath.basename(rel)
    return not (base.startswith("test_") or base == "conftest.py" or "/tests/" in f"/{rel}"
                or "__pycache__" in rel or rel.startswith(("tmp/", "data/", "uploads/")))


def check_range(src: Source, apps: dict, since: str) -> tuple[list[str], list[str]]:
    """Code and Help are one release unit: every functional commit after `since` has its Help in the range."""
    until = src.rev or "HEAD"
    errors, warnings = [], []
    changed = set(src.git("diff", "--name-only", f"{since}..{until}").splitlines())
    added = set(src.git("diff", "--name-only", "--diff-filter=A", f"{since}..{until}").splitlines())
    units = []                                   # (label, files): each functional unit of the release
    for commit in src.git("rev-list", "--reverse", f"{since}..{until}").split():
        if not TECHNICAL.search(src.git("show", "-s", "--format=%B", commit)):
            units.append((commit[:10], src.git("show", "--name-only", "--format=", commit).splitlines()))
    if not src.rev:                              # uncommitted work counts too, as one more unit
        local = set(src.git("diff", "--name-only", "HEAD").splitlines())
        local |= set(src.git("ls-files", "--others", "--exclude-standard", "--", "03 Software").splitlines())
        changed |= local
        added |= set(src.git("ls-files", "--others", "--exclude-standard", "--", "03 Software").splitlines())
        units.append(("working tree", sorted(local)))
    for app_name, app in apps.items():
        templates = app["templates"].rstrip("/")
        help_targets = {name: {f"{templates}/{t.partition('#')[0]}" for t in targets(entry)}
                        for name, entry in app.get("pages", {}).items()}
        guides = set().union(*help_targets.values())
        for name in app.get("help_missing", {}):
            if f"{templates}/{name}" in added:
                errors.append(f"{app_name}: new page {name} was put in help_missing: a new page needs its Help")
        for name, reason in app.get("not_operational", {}).items():
            if f"{templates}/{name}" in added:
                warnings.append(f"{app_name}: new page {name} is classified not operational ({reason}): confirm it")
        for short, unit_files in units:
            files = [f for f in unit_files if functional(app, f) and f not in guides]
            other = []                           # code, layouts, assets: not one page's own template
            for path in files:
                name = path[len(templates) + 1:] if path.startswith(templates + "/") else None
                if name in help_targets:
                    if not help_targets[name] & changed:
                        errors.append(f"{app_name}: {short} changes page {name} but its Help "
                                      f"{', '.join(sorted(help_targets[name]))} is not updated in this release")
                elif name in app.get("help_missing", {}):
                    errors.append(f"{app_name}: {short} changes page {name}, which has no Help yet: write its "
                                  f"How Works section, or declare the commit 'How-Works: technical - <reason>'")
                else:
                    other.append(path)
            if other and not guides & changed:
                errors.append(f"{app_name}: {short} changes {', '.join(other[:3])}{' …' if len(other) > 3 else ''} "
                              f"but no {app_name} Help is updated in this release"
                              + ("" if guides else f" ({app_name} has no How Works Help yet)")
                              + "; or declare the commit 'How-Works: technical - <reason>'")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app", action="append", help="check only this app (repeatable)")
    parser.add_argument("--rev", help="read this commit instead of the working tree")
    parser.add_argument("--since", help="released commit: also check Help updates of every later commit")
    parser.add_argument("--report", action="store_true", help="also list pages still without Help")
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    src = Source(Path(args.root), args.rev)
    if not src.exists(REGISTRY):
        print(f"ERROR: {REGISTRY} not found" + (f" in {args.rev}" if args.rev else ""))
        return 1
    apps = json.loads(src.read(REGISTRY))["apps"]
    unknown = [a for a in args.app or [] if a not in apps]
    if unknown:
        print(f"ERROR: unknown app(s) {unknown}; registry apps: {sorted(apps)}")
        return 1
    apps = {k: v for k, v in apps.items() if not args.app or k in args.app}
    errors, warnings = check_tree(src, apps, args.report)
    if args.since:
        range_errors, range_warnings = check_range(src, apps, args.since)
        errors += range_errors
        warnings += range_warnings
    for w in warnings:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    covered = sum(len(a.get("pages", {})) for a in apps.values())
    missing = sum(len(a.get("help_missing", {})) for a in apps.values())
    print(f"How Works: {covered} page(s) with Help, {missing} still without, {len(errors)} error(s)"
          + (f" [{args.rev[:12]}]" if args.rev else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
