"""Local SMTP configuration for Selection, protected with Windows DPAPI.

The file lives in %LOCALAPPDATA%\\RF-One\\Selection\\smtp.json — outside
OneDrive and Git. Host, port and user name are stored in clear; the password
is stored only as a DPAPI blob bound to the current Windows user, so the file
is useless if copied to another account or PC. Written by
`configure_smtp.py local`, read by `local_server.py`; the password never
appears in code, in the console or in a log.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
import sys
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Selection" / "smtp.json"
_ENTROPY = b"RF-One Selection SMTP"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("The local SMTP configuration is protected with Windows DPAPI: Windows only.")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    source = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    entropy = _Blob(len(_ENTROPY), ctypes.cast(ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY)),
                                               ctypes.POINTER(ctypes.c_char)))
    result = _Blob()
    call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = call(ctypes.byref(source), "RF-One Selection SMTP", ctypes.byref(entropy), None, None, 0x1,
                  ctypes.byref(result))
    else:
        ok = call(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(result))
    if not ok:
        raise RuntimeError("Windows could not protect/unprotect the SMTP password (DPAPI).")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def save(*, host: str, port: int, username: str, password: str) -> Path:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"host": host, "port": port, "username": username,
               "password_dpapi": base64.b64encode(_dpapi(password.encode("utf-8"), protect=True)).decode("ascii")}
    CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return CONFIG_FILE


def apply_to_environment() -> bool:
    """Sets the RFONE_SMTP_* variables from the protected file, if present.
    Returns False (and changes nothing) when there is no file."""
    if not CONFIG_FILE.exists():
        return False
    data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    os.environ["RFONE_SMTP_HOST"] = data["host"]
    os.environ["RFONE_SMTP_PORT"] = str(data["port"])
    os.environ["RFONE_SMTP_USERNAME"] = data["username"]
    os.environ["RFONE_SMTP_PASSWORD"] = _dpapi(base64.b64decode(data["password_dpapi"]), protect=False).decode("utf-8")
    return True
