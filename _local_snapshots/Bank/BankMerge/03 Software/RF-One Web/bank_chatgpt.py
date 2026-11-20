"""Bank conversation through the existing ChatGPT login; no provider fallback."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

PROVIDER = 'OPENAI_CHATGPT_CODEX'


def model():
    return 'ChatGPT account default'


def generate_json(prompt, *, web_research=False):
    exe = shutil.which('codex')
    if not exe:
        candidates = list((Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI/Codex/bin').glob('*/codex.exe'))
        exe = str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else None
    if not exe:
        raise AIProviderUnavailable('Codex is unavailable. Sign in with ChatGPT on this PC.')
    with tempfile.TemporaryDirectory(prefix='rfone-bank-chatgpt-') as folder:
        output = Path(folder) / 'answer.json'
        command = [exe, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                   '--sandbox', 'read-only', '-C', folder, '-c', 'model_provider="openai"',
                   '-c', 'features.shell_tool=false', '-c', 'features.exec_tool=false',
                   '-c', 'web_search="live"' if web_research else 'web_search="disabled"', '-c', 'project_doc_max_bytes=0',
                   '--output-last-message', str(output), '-']
        try:
            result = subprocess.run(command, input=('Answer only with the requested JSON object. Use web search to verify sources; do not use any other tools.\n' if web_research else 'Answer only with the requested JSON object. Do not use tools.\n')+prompt,
                                    text=True, encoding='utf-8', capture_output=True, timeout=180,
                                    creationflags=0x08000000 if os.name == 'nt' else 0)
            if result.returncode != 0 or not output.exists():
                raise AIProviderUnavailable('ChatGPT did not complete the response. Check Codex sign-in and connection.')
            value = output.read_text(encoding='utf-8').strip()
            if value.startswith('```'):
                value = value.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            answer = json.loads(value)
            if not isinstance(answer, dict):
                raise ValueError('Expected an object')
            return answer
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise AIProviderUnavailable('ChatGPT response unavailable or unreadable. No changes applied.') from exc
