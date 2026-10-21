"""Refresh only the existing local chat assets, without touching routes/data."""
from pathlib import Path
import shutil

source=Path(__file__).resolve().parent
target=Path('C:/Users/servi/OneDrive/AI-RF-ONE/rf-one-bank-simple-who-rules/03 Software/RF-One Web/static/bank-assistant')
assert (target/'app.js').exists()
script=(source/'app.js').read_text(encoding='utf-8')
script=script.replace("'snapshot.json'","'/bank/ai-rules/snapshot'")
script=script.replace('rfone-bank-assistant-chat-v1','rfone-bank-assistant-local-chat-v1')
(target/'app.js').write_text(script,encoding='utf-8')
shutil.copy2(source/'preview.css',target/'preview.css')
print('Chat assets refreshed. Operational data unchanged.')
