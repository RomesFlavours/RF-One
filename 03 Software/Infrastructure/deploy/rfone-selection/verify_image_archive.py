"""Verify OCI blobs, rootfs layers and frozen application bytes without running code."""
import argparse
import gzip
import hashlib
import json
import tarfile
import subprocess
from pathlib import Path


def digest(stream):
    return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(archive_path, source):
    expected = {}
    app_prefix = '03 Software/AWSSelection/'
    manifest = json.loads((source / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for name, value in manifest.items():
        if name.startswith(app_prefix) and not Path(name).name.startswith('test_'):
            expected['app/' + name[len(app_prefix):]] = value
    deploy = source / '03 Software/Infrastructure/deploy/rfone-selection'
    for name in ['server_entrypoint.py', 'requirements-linux.lock']:
        expected['app/' + name] = hashlib.sha256((deploy / name).read_bytes()).hexdigest()
    observed, forbidden = {}, []
    with tarfile.open(archive_path, 'r') as archive:
        def blob(descriptor):
            algorithm, value = descriptor['digest'].split(':', 1)
            assert algorithm == 'sha256'
            path = 'blobs/sha256/' + value
            with archive.extractfile(path) as stream:
                assert digest(stream) == value, 'Corrupted OCI blob: ' + value
            return path

        def read_blob(descriptor):
            return json.load(archive.extractfile(blob(descriptor)))

        index = json.load(archive.extractfile('index.json'))
        descriptor = next(d for d in index['manifests'] if d.get('platform', {}).get('architecture', 'amd64') == 'amd64')
        image = read_blob(descriptor)
        while 'manifests' in image:
            descriptor = next(d for d in image['manifests'] if d.get('platform', {}).get('architecture', 'amd64') == 'amd64')
            image = read_blob(descriptor)
        config = read_blob(image['config'])
        assert config['os'] == 'linux' and config['architecture'] == 'amd64'
        assert config['config']['Labels']['org.opencontainers.image.revision'] == subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        assert config['config']['Entrypoint'] == ['python', '/app/server_entrypoint.py']
        assert 'app:app' in config['config']['Cmd']
        assert '8080/tcp' in config['config']['ExposedPorts']
        for value in config['config'].get('Env', []):
            assert value.split('=', 1)[0] not in {'RFONE_DATABASE_URL', 'OPENAI_API_KEY', 'RFONE_SELECTION_OPENAI_API_KEY', 'RFONE_FLASK_SECRET_KEY'}, 'Credential baked into image'
        layers = image['layers']
        assert len(layers) == len(config['rootfs']['diff_ids'])
        for layer, diff_id in zip(layers, config['rootfs']['diff_ids']):
            path = blob(layer)
            def open_layer():
                stream = archive.extractfile(path)
                return gzip.GzipFile(fileobj=stream) if layer['mediaType'].endswith('+gzip') or layer['mediaType'].endswith('.gzip') else stream
            with open_layer() as stream:
                assert 'sha256:' + digest(stream) == diff_id, 'Invalid rootfs layer'
            with open_layer() as stream, tarfile.open(fileobj=stream, mode='r|') as filesystem:
                for member in filesystem:
                    name = member.name.removeprefix('./').lstrip('/')
                    if '/.wh.' in name:
                        observed.pop(name.replace('/.wh.', '/'), None)
                    if name in expected and member.isfile():
                        observed[name] = digest(filesystem.extractfile(member))
                    if name.startswith('app/') and member.isfile():
                        if (name.startswith(('app/Selection/uploads/', 'app/Selection/data/', 'app/RF-One Data Store/data/'))
                                or Path(name).name.startswith('.env')
                                or name in {'app/Selection/local_server.py', 'app/Selection/local_runtime.py', 'app/Selection/smtp_local_config.py'}
                                or (name.startswith('app/Selection/test_') and name.endswith('.py'))):
                            forbidden.append(name)
        assert not forbidden, forbidden
        assert observed == expected, {'missing': sorted(set(expected) - set(observed)), 'changed': [p for p in observed if observed[p] != expected[p]]}
    return {'linux_amd64': True, 'oci_manifest': descriptor['digest'], 'image_config': image['config']['digest'],
            'source_commit': config['config']['Labels']['org.opencontainers.image.revision'],
            'application_files_verified': len(expected), 'layers_verified': len(layers), 'no_operational_files_or_credentials': True,
            'archive_sha256': digest(archive_path.open('rb'))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.archive, args.source)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
