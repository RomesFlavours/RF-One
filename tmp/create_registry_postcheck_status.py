from pathlib import Path
p=Path('tmp/status_registry_aws_audit.py');s=p.read_text(encoding='utf-8').replace("state['audit_task']","state['post_audit_task']").replace("'aws-audit.log'","'aws-post-audit.log'").replace("'aws-audit.json'","'aws-post-audit.json'").replace("state['audit_verified']","state['post_audit_verified']")
Path('tmp/status_registry_aws_postcheck.py').write_text(s,encoding='utf-8',newline='\n')
