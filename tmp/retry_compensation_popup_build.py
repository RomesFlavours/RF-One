from pathlib import Path
import boto3,json,zipfile,hashlib
root=Path('tmp/compensation-popup-release');p=root/'state.json';d=json.loads(p.read_text());context=root/'context';docker=context/'Dockerfile';lines=docker.read_text().splitlines();lines[1]='COPY ["templates/compensation_run_detail.html", "/app/RF-One Web/templates/compensation_run_detail.html"]';lines[2]='COPY ["static/js/compensation-checks.js", "/app/RF-One Web/static/js/compensation-checks.js"]';docker.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
archive=root/'source-v2.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for file in context.rglob('*'):
  if file.is_file():z.write(file,file.relative_to(context).as_posix())
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');cb=s.client('codebuild');old=cb.batch_get_builds(ids=[d['build_id']])['builds'][0];key=d['source_s3_key'].replace('/source.zip','/source-v2.zip');s.client('s3').upload_file(str(archive),'rfone-tips-deploy-418674484214',key);result=cb.start_build(projectName='rfone-web-build',sourceLocationOverride='rfone-tips-deploy-418674484214/'+key,buildspecOverride=old['source']['buildspec']);d.setdefault('failed_build_ids',[]).append(d['build_id']);d.update(build_id=result['build']['id'],source_s3_key=key,source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),build_status='IN_PROGRESS');p.write_text(json.dumps(d,indent=2));print('Popup build restarted with JSON COPY paths:',d['build_id'])
