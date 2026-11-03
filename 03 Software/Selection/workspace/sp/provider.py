"""CV Selection SP transport only. Does not change the shared provider registry.

Secrets are injected into the process; no dotenv/API key files are read here.
Real CV traffic is closed until the account data-control review is recorded.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
import socket
import time
import urllib.error
import urllib.request

from rfone_data_store.selection.parsing import ai_client
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

MODEL = "gpt-6.1-terra"
HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
ENDPOINT = "https://api.openai.com/v1/responses"
_SCOPE = ContextVar("selection_sp_transport", default=False)
_LAST = ContextVar("selection_sp_last_provider", default=None)
_USAGE = ContextVar("selection_sp_usage", default=None)


@contextmanager
def scope():
    token = _SCOPE.set(True)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def in_scope():
    return _SCOPE.get()


def provider():
    value = os.environ.get("RFONE_SP_AI_PROVIDER", "OPENAI").strip().upper()
    if value not in ("OPENAI", "BEDROCK"):
        raise AIProviderUnavailable("RFONE_SP_AI_PROVIDER must be OPENAI or BEDROCK.")
    return value


def label():
    return _LAST.get() or (f"OpenAI · {MODEL}" if provider() == "OPENAI" else f"AWS Bedrock · {HAIKU}")


def _authorize(selected):
    # Synthetic traffic is an explicit test setting, never enabled by the application.
    if os.environ.get("RFONE_SP_SYNTHETIC_ONLY") == "1":
        return
    review = os.environ.get("RFONE_SP_DATA_REVIEWED", "")
    expected = "openai-api-reviewed" if selected == "OPENAI" else "bedrock-reviewed"
    if expected not in review.split(","):
        raise AIProviderUnavailable("SP CV processing blocked: account retention/data controls have not been reviewed.")


def _windows_user_key():
    """Read the existing user's secret when the desktop process predates its creation.
    Never write the registry, log the value, or read a repository dotenv file.
    Non-Windows services use the injected process secret only.
    """
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in ("RFONE_SP_OPENAI_API_KEY", "OPENAI_API_KEY"):
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                except OSError:
                    continue
    except OSError:
        pass
    return None


def _api_key():
    return (os.environ.get("RFONE_SP_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
            or _windows_user_key())


def _post(payload, timeout):
    key = _api_key()
    if not key:
        raise AIProviderUnavailable("OpenAI secret is not configured in the process environment.")
    request = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(),
        {"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Never include upstream bodies, request headers or CV text in an error/log.
        raise TransportError(f"OpenAI HTTP {exc.code}", retryable=exc.code == 429 or exc.code >= 500) from None
    except (TimeoutError, socket.timeout):
        raise TransportError("OpenAI timeout", retryable=True, timed_out=True) from None
    except urllib.error.URLError as exc:
        timed_out = isinstance(exc.reason, (TimeoutError, socket.timeout))
        raise TransportError("OpenAI timeout" if timed_out else "OpenAI connection error", retryable=True,
                             timed_out=timed_out) from None
    except (ValueError, OSError):
        raise AIProviderUnavailable("OpenAI returned an unreadable response.") from None


class TransportError(AIProviderUnavailable):
    def __init__(self, message, *, retryable=False, timed_out=False):
        super().__init__(message)
        # A timed-out request is still billed by the provider and would most likely time out again: never repeated.
        self.retryable = retryable
        self.timed_out = timed_out


SCAN_TIMEOUT_SECONDS = 25
QUICK_SECONDS = 5


def _openai(content, *, json_output, scanned=False, attempts=None):
    payload = {"model": MODEL, "store": False, "reasoning": {"effort": "none"},
               "max_output_tokens": 16000, "input": [{"role": "user", "content": content}]}
    if json_output:
        payload["text"] = {"format": {"type": "json_object"}}
    # Text runs in the background (queue, Read again): 90 s, the queue repeats it while the provider is busy.
    # Scans run inside the upload request: 25 s (several pages are copied word for word), and a second attempt only
    # after a quick refusal (429/5xx within 5 s), never after a timeout, so the request ends before CloudFront's 60 s.
    attempts, timeout = (attempts or (2 if scanned else 1)), (SCAN_TIMEOUT_SECONDS if scanned else 90)
    started = time.monotonic()
    for attempt in range(attempts):
        try:
            response = _post(payload, timeout)
            break
        except TransportError as exc:
            if (not exc.retryable or exc.timed_out or attempt + 1 == attempts
                    or time.monotonic() - started > QUICK_SECONDS):
                raise
            time.sleep(1)
    if response.get("status") != "completed":
        raise AIProviderUnavailable("OpenAI response incomplete or refused.")
    text = "".join(block.get("text", "") for item in response.get("output", [])
                   for block in item.get("content", []) if block.get("type") == "output_text")
    if not text.strip():
        raise AIProviderUnavailable("OpenAI returned no text.")
    _LAST.set(f"OpenAI · {MODEL}")
    _USAGE.set(response.get("usage", {}))
    return text


def _bedrock(prompt, images=None, *, attempts=None):
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        raise AIProviderUnavailable("The boto3 package is required for Haiku fallback.") from None
    content = [{"image": {"format": "jpeg", "source": {"bytes": b}}} for b in images or []]
    content.append({"text": prompt})
    # Pin Haiku independently of the shared domains' model configuration.
    attempts = attempts or (2 if images else 1)
    for attempt in range(attempts):
        try:
            # A session of its own: boto3's default session is not safe to share between the queue's threads.
            client = boto3.session.Session().client(
                "bedrock-runtime", region_name=ai_client._read_env_or_dotenv("AWS_REGION"),
                config=Config(connect_timeout=3, read_timeout=SCAN_TIMEOUT_SECONDS if images else 90,
                              retries={"total_max_attempts": 1, "mode": "standard"}))
            result = client.converse(modelId=HAIKU, messages=[{"role": "user", "content": content}],
                                      inferenceConfig={"maxTokens": 16000, "temperature": 0})
            if result.get("stopReason") not in (None, "end_turn", "stop_sequence"):
                raise AIProviderUnavailable("Bedrock response incomplete.")
            _LAST.set(f"AWS Bedrock · {HAIKU}")
            return "".join(b.get("text", "") for b in result["output"]["message"]["content"])
        except (BotoCoreError, ClientError) as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            # Throttling, a busy service or a timeout passes; access or configuration errors do not.
            timed_out = not code and "timeout" in exc.__class__.__name__.lower()
            retryable = code in _BEDROCK_TRANSIENT or timed_out
            if attempt + 1 == attempts or not retryable or timed_out:
                raise TransportError(f"SP Bedrock request failed ({code or exc.__class__.__name__}).",
                                     retryable=retryable, timed_out=timed_out) from None
            time.sleep(1)


_BEDROCK_TRANSIENT = ("ThrottlingException", "ServiceUnavailableException", "InternalServerException",
                      "ModelNotReadyException")


def _run(prompt, images=None, *, json_output=True):
    selected = provider()
    _authorize(selected)
    started = time.monotonic()
    try:
        if selected == "BEDROCK":
            return _bedrock(prompt, images)
        content = [{"type": "input_text", "text": prompt}]
        content += [{"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}
                    for b in images or []]
        return _openai(content, json_output=json_output, scanned=bool(images),
                       attempts=1 if os.environ.get("RFONE_SP_AI_FALLBACK", "").upper() == "BEDROCK" else None)
    except TransportError as exc:
        # Opt-in only, and only for transient provider failures. Never mask authentication/configuration errors.
        if (selected != "OPENAI" or not exc.retryable
                or os.environ.get("RFONE_SP_AI_FALLBACK", "").upper() != "BEDROCK"
                or (images and (exc.timed_out or time.monotonic() - started > QUICK_SECONDS))):
            raise         # a scan in an upload request has no time left for a second provider
        _authorize("BEDROCK")
        return _bedrock(prompt, images, attempts=1)


def generate_json(prompt):
    text = _run(prompt)
    try:
        result = json.loads(ai_client._strip_markdown_json_fence(text))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except ValueError:
        raise AIProviderUnavailable("SP AI returned unparsable JSON.") from None


def transcribe(images, prompt):
    return _run(prompt, images, json_output=False).strip()


def last_usage():
    return dict(_USAGE.get() or {})
