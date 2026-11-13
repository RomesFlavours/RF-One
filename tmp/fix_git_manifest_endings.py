from pathlib import Path
import zipfile,json
r=Path('tmp/git-anagrafica-release');p=r/'07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_MANIFEST.json';d=json.loads(p.read_text())
with zipfile.ZipFile('tmp/anagrafica-release/source.zip') as z:
 for name in z.namelist():
  b=z.read(name)
  if b'\x00' in b:continue
  try:b.decode('utf-8-sig')
  except UnicodeDecodeError:continue
  if b'\n' in b:d['text_endings'][name]='CRLF' if b'\r\n' in b else 'LF'
p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
