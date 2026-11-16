"""Create an isolated, allowlisted Git snapshot and Docker context; never publish."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from pathlib import Path


def copy_tree(source, target, extensions):
    for item in source.rglob('*'):
        if item.is_file() and item.suffix in extensions and '__pycache__' not in item.parts:
            destination = target / item.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dependency-lock', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.repository.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit('Refusing to overwrite an existing frozen release.')
    source = output / 'source'
    app_root = Path('03 Software/AWSSelection')
    for directory, extensions in [('Selection/workspace', {'.py'}), ('Selection/templates', {'.html'}),
                                  ('Selection/static', {'.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.woff', '.woff2'}),
                                  ('Selection/locales', {'.json'}), ('RF-One Data Store/rfone_data_store', {'.py', '.csv'}),
                                  ('RF-One Data Store/migrations', {'.py', '.mako'}),
                                  # Frozen catalogue inputs read by historical revisions (fix A3): no personal data.
                                  ('RF-One Data Store/migrations/migration_data', {'.csv', '.md'})]:
        copy_tree(root / app_root / directory, source / app_root / directory, extensions)
    migration_data = source / app_root / 'RF-One Data Store/migrations/migration_data'
    referenced = set()
    for revision in (source / app_root / 'RF-One Data Store/migrations/versions').glob('*.py'):
        referenced.update(re.findall(r'migration_data["\'/,\s]+["\']?([\w.-]+\.csv)', revision.read_text(encoding='utf-8')))
    missing = sorted(name for name in referenced if not (migration_data / name).is_file())
    if missing:
        raise SystemExit('Migration inputs missing from the release: ' + repr(missing))
    for directory, names in [('Selection', ['app.py', 'local_i18n.py', 'requirements.txt']),
                             ('RF-One Data Store', ['requirements.txt', 'alembic.ini', 'MIGRATIONS.md'])]:
        for name in names:
            relative = app_root / directory / name
            shutil.copyfile(root / relative, source / relative)
    for test in (root / app_root / 'Selection').glob('test_*.py'):
        shutil.copyfile(test, source / app_root / 'Selection' / test.name)
    deploy = Path('03 Software/Infrastructure/deploy/rfone-selection')
    for name in ['Dockerfile', 'server_entrypoint.py', 'cloud-runtime.example.json', 'LOCAL_RELEASE.md', 'freeze_local_release.py', 'verify_linux_release.py', 'mock_s3_local.py', 'verify_image_archive.py', 'instance-policy-openai.example.json', 'verify_http_release.py', 'test_session_safety.py']:
        target = source / deploy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / deploy / name, target)
    shutil.copyfile(args.dependency_lock, source / deploy / 'requirements-linux.lock')
    copy_tree(root / '03 Software/Infrastructure/selection-migration', source / '03 Software/Infrastructure/selection-migration', {'.py', '.md', '.json'})
    for name in ['check_how_works.py', 'how_works_registry.json', 'How Works Standard.md', 'Development Language Policy.md']:
        relative = Path('03 Software/Shared UI') / name
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, source / relative)
    for name in ['CLAUDE.md', 'AGENTS.md']:
        shutil.copyfile(root / name, source / name)
    files = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in source.rglob('*') if p.is_file()}
    forbidden = [name for name in files if Path(name).suffix in ('.db', '.sqlite', '.exe', '.pem', '.key') or '/uploads/' in name or '/data/' in name or Path(name).name.startswith('.env')]
    if forbidden:
        raise SystemExit('Forbidden release files: ' + repr(forbidden))
    (source / 'SOURCE_MANIFEST.json').write_text(json.dumps(files, indent=2) + '\n', encoding='utf-8')
    def git(*arguments):
        return subprocess.check_output(['git', *arguments], cwd=source, text=True).strip()
    git('init', '-b', 'codex/selection-release')
    git('config', 'core.autocrlf', 'false')
    git('add', '.')
    git('-c', 'user.name=Codex', '-c', 'user.email=codex@local.invalid', 'commit', '-m', 'Freeze Selection Linux release and migration tooling')
    commit = git('rev-parse', 'HEAD')
    git('bundle', 'create', str(output / 'source.bundle'), '--all')
    assert not git('status', '--porcelain'), 'Frozen source changed'
    context = output / 'context'
    shutil.copytree(source / app_root, context, ignore=shutil.ignore_patterns('test_*.py'))
    for name in ['Dockerfile', 'server_entrypoint.py', 'requirements-linux.lock']:
        shutil.copyfile(source / deploy / name, context / name)
    (context / '.dockerignore').write_text('**/__pycache__/\n**/*.pyc\n**/.env*\n**/*.db\n**/*.sqlite*\n**/uploads/\n**/data/\n.git/\n', encoding='utf-8')
    for filename, directory in [('build-context.tar', context), ('source.tar', source)]:
        with tarfile.open(output / filename, 'w') as archive:
            for item in sorted(directory.rglob('*')):
                if item.is_file() and '.git' not in item.relative_to(directory).parts:
                    archive.add(item, arcname=item.relative_to(directory).as_posix())
    manifest = {'source_commit': commit, 'source_files': len(files), 'aws_modified': False,
                'artifacts': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ['build-context.tar', 'source.tar', 'source.bundle']}}
    (output / 'release-source.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
