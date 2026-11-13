from pathlib import Path
import json,zipfile
root=Path.cwd();target=root/'tmp/git-anagrafica-release';manifest_path=target/'07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_MANIFEST.json';manifest=json.loads(manifest_path.read_text());manifest['text_endings']={}
with zipfile.ZipFile(root/'tmp/anagrafica-release/source.zip') as z:
 for name in z.namelist():
  b=z.read(name)
  if Path(name).suffix in ('.py','.html','.js','.css','.json','.md','.txt','.ini','.yml','.csv'):
   manifest['text_endings'][name]='CRLF' if b'\r\n' in b else 'LF'
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
attrs=target/'.gitattributes';t=attrs.read_text(encoding='utf-8') if attrs.exists() else '';t+='\n# Runtime release artifacts and guard hashes require stable LF source files.\n';t+='\n'.join('"03 Software/**/*'+ext+'" text eol=lf' for ext in ('.py','.html','.js','.css','.json','.md','.txt','.ini','.yml'))+'\n';attrs.write_text(t,encoding='utf-8')
