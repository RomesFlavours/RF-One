from pathlib import Path
import shutil
base=Path(r'tmp/git-anagrafica-release/03 Software')
p=base/'RF-One Data Store/rfone_data_store/rfone_web_session.py';s=p.read_text(encoding='utf-8').replace('''    if account is None:
        return None
    if session_version''','''    if account is None or account.status != ACTIVE_ACCOUNT_STATUS:
        return None
    if session_version''');p.write_text(s,encoding='utf-8',newline='\n')
frozen=Path(r'C:/Users/servi/OneDrive/AI-RF-ONE/RF One/output/kitchen-release/source/03 Software/RF-One Web/templates')
for src in frozen.glob('*kitchen*'):
 dst=base/'RF-One Web/templates'/src.name
 if not dst.exists():shutil.copy2(src,dst)
