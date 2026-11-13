"""Bank AI Rules interpreted automatically by the local Claude Code CLI
(BANK_AI_RULES_012) — SESSION mode, no copy-and-paste between Bank and VS Code.

In SESSION mode Bank never calls an AI provider (AWS). Until now a rule text
with no saved interpretation made the preview WAIT for a person to run the
session tool. When the local environment enables it
(`RFONE_BANK_CLAUDE_CODE_CLI`), the preview instead asks the Claude Code CLI
installed on this PC — the same program and the same login the VS Code
session uses — in print mode, with NO tools, from a neutral folder, and with
no session kept: it receives the exact interpretation prompt and answers
with JSON. RF-One validates the answer with the same validator as always
(an incomplete or partial interpretation is BLOCKED) and saves it in the
interpretation cache; the preview then runs by code in the same request.

  RFONE_BANK_CLAUDE_CODE_CLI    unset / "" / "off": not used (the preview
                                waits for the session, as before);
                                "auto": the CLI of the newest Claude Code
                                VS Code extension, else `claude` on PATH;
                                otherwise the path of the executable.
  RFONE_BANK_CLAUDE_CODE_MODEL  the model asked for (default claude-opus-5-5).

The CLI is a commodity behind this one function (`generate_json`): replacing
it changes nothing else in Bank.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..selection.parsing import ai_client

PROVIDER = "CLAUDE_CODE_CLI"
DEFAULT_MODEL = "claude-opus-5-5"
TIMEOUT_SECONDS = 300
SYSTEM_PROMPT = ("You translate one bank-reconciliation rule into the JSON structure the user message describes. "
                 "Answer with that JSON object only — no markdown, no comments, no other text.")


def configured() -> str:
    return (os.environ.get("RFONE_BANK_CLAUDE_CODE_CLI") or "").strip()


def model() -> str:
    return (os.environ.get("RFONE_BANK_CLAUDE_CODE_MODEL") or DEFAULT_MODEL).strip()


def executable() -> str | None:
    """The CLI to run, or None when automation is off or no CLI is found."""
    value = configured()
    if not value or value.lower() in ("off", "0", "no", "false"):
        return None
    if value.lower() != "auto":
        return value if Path(value).is_file() else None
    pattern = os.path.join(os.path.expanduser("~"), ".vscode", "extensions", "anthropic.claude-code-*",
                           "resources", "native-binary", "claude.exe")
    found = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p))
    if found:
        return found[-1]
    return shutil.which("claude")


def available() -> bool:
    return executable() is not None


def _workdir() -> str:
    """A neutral, empty folder: no project instructions or files are read."""
    path = os.path.join(tempfile.gettempdir(), "rfone-bank-claude-code-cli")
    os.makedirs(path, exist_ok=True)
    return path


def _run(exe: str, prompt: str) -> str:
    """The CLI's JSON envelope (stdout). Separate so tests can replace it."""
    flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
    result = subprocess.run(
        [exe, "-p", "--output-format", "json", "--model", model(), "--tools", "", "--no-session-persistence",
         "--system-prompt", SYSTEM_PROMPT],
        input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS, cwd=_workdir(),
        creationflags=flags)
    if result.returncode != 0 and not result.stdout.strip():
        raise ai_client.AIProviderUnavailable(
            f"Claude Code CLI exited with code {result.returncode}: {(result.stderr or '').strip()[:300]}")
    return result.stdout


def _json_object(text: str) -> dict:
    text = (text or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("the answer is not a JSON object")
    return value


def generate_json(prompt: str) -> dict:
    """The interpretation the CLI gives for `prompt` (a dict), or
    `AIProviderUnavailable` with the concrete reason (no CLI, not logged in,
    timeout, an answer that is not JSON)."""
    exe = executable()
    if exe is None:
        raise ai_client.AIProviderUnavailable("the Claude Code CLI is not enabled or not found on this PC")
    try:
        envelope = json.loads(_run(exe, prompt))
    except subprocess.TimeoutExpired as exc:
        raise ai_client.AIProviderUnavailable(f"Claude Code CLI did not answer within {TIMEOUT_SECONDS} s") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise ai_client.AIProviderUnavailable(f"Claude Code CLI could not be run or read: {exc}") from exc
    if envelope.get("is_error") or envelope.get("subtype") not in (None, "success"):
        raise ai_client.AIProviderUnavailable(
            "Claude Code CLI answered with an error (e.g. login expired: open Claude Code in VS Code and sign in): "
            + str(envelope.get("result") or envelope.get("subtype"))[:300])
    try:
        return _json_object(envelope.get("result") or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ai_client.AIProviderUnavailable(f"Claude Code CLI did not answer with JSON: {exc}") from exc
