"""Local Windows credential vault. DB stores opaque references, not passwords.

Windows DPAPI binds ciphertext to the current Windows user. Web and worker must
run as that same user. No AWS calls or secret creation during local development.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import uuid


class CredentialError(Exception):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data, *, decrypt=False):
    if os.name != 'nt':
        raise CredentialError('CREDENTIALS_UNAVAILABLE')
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                  ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise CredentialError('CREDENTIALS_UNAVAILABLE')
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        if target.pbData:
            ctypes.memset(target.pbData, 0, target.cbData)
            kernel.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))
        ctypes.memset(buffer, 0, len(data))


class LocalMailboxVault:
    def __init__(self, directory=None):
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'RF-One' / 'mailbox-secrets'
        self.directory = Path(directory) if directory else base

    def _path(self, ref):
        if not re.fullmatch(r'local:[a-f0-9]{32}', ref or ''):
            raise CredentialError('CREDENTIALS_UNAVAILABLE')
        return self.directory / (ref[6:] + '.dpapi')

    def save(self, password):
        if not isinstance(password, str) or not password or len(password) > 4096 or '\x00' in password:
            raise CredentialError('CREDENTIALS_UNAVAILABLE')
        encrypted = _dpapi(password.encode('utf-8'))
        self.directory.mkdir(parents=True, exist_ok=True)
        ref = 'local:' + uuid.uuid4().hex
        try:
            with self._path(ref).open('xb') as target:
                target.write(encrypted)
            return ref
        except OSError:
            raise CredentialError('CREDENTIALS_UNAVAILABLE') from None

    def load(self, ref):
        try:
            return _dpapi(self._path(ref).read_bytes(), decrypt=True).decode('utf-8')
        except (OSError, UnicodeError):
            raise CredentialError('CREDENTIALS_UNAVAILABLE') from None

    def delete(self, ref):
        try:
            self._path(ref).unlink(missing_ok=True)
        except OSError:
            # An orphaned encrypted file is preferable to rolling back a saved configuration.
            pass
