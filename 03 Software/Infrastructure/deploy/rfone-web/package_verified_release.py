"""Rebuild and verify the exact source bytes listed by an AWS release manifest.

Usage: python package_verified_release.py --manifest <manifest.json> --output <file.zip>
The output contains only allowlisted runtime files; never database/local state.
"""
from pathlib import Path
import argparse,hashlib,json,zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[4]
    software=repo/'03 Software'
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    entries=[]
    for name,digest in manifest['files'].items():
        source=software/'Infrastructure/deploy/rfone-web/Dockerfile' if name=='Dockerfile' else software/name
        if not source.resolve().is_relative_to(software.resolve()):raise ValueError('Invalid release path')
        payload=source.read_bytes()
        ending=manifest.get('text_endings',{}).get(name)
        if ending:
            payload=payload.replace(b'\r\n',b'\n')
            if ending=='CRLF':payload=payload.replace(b'\n',b'\r\n')
        if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Release content mismatch: '+name)
        entries.append((name,payload))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,payload in entries:archive.writestr(name,payload)
    print('Verified and packaged '+str(len(entries))+' runtime files.')


if __name__=='__main__':main()
