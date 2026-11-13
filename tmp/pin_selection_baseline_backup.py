from pathlib import Path
import json
root=Path('tmp/registry-access-release');state=json.loads((root/'release-state.json').read_text());p=Path('tmp/git-anagrafica-release/03 Software/Infrastructure/deploy/registry-authorization/manifest.json');manifest=json.loads(p.read_text());baseline=manifest['services']['selection']['baseline'];baseline['original_source']=baseline['source'];baseline['source']='rfone-tips-deploy-418674484214/'+state['services']['selection']['baseline_backup_s3_key'];p.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
