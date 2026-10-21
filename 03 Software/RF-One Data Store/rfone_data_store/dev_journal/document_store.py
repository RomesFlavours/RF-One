"""Where Development Journal documents are kept — the same two-store choice
Selection makes for résumés (`selection/document_store.py`), under its own
prefix so the two archives never mix:

- S3 (deployment): `RFONE_DEV_JOURNAL_DOCUMENT_BUCKET` names a PRIVATE
  bucket; each file is stored once, server-side encrypted, under
  `dev-journal/documents/<uuid>`. `storage_path` is `s3://<bucket>/<key>`.
  On AWS this is the private Selection document bucket.
- LOCAL (development only): `RFONE_DEV_JOURNAL_DOCUMENT_DIR` names a
  persistent folder, set explicitly — the local launcher
  (`RF-One Web/local_server.py`) and the tests do. `storage_path` is
  `local:<uuid>`.

With neither set there is NO store: uploads fail with a clear message and
nothing is written to the service's own disk (App Runner's disk is
ephemeral; a document saved there would silently disappear).

Files are never public: the key is a random id (the person's file name is
never part of a path), and the app reads and serves the bytes itself,
behind the RF-One login and the Development Journal access.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

BUCKET_ENV_VAR = "RFONE_DEV_JOURNAL_DOCUMENT_BUCKET"
DIR_ENV_VAR = "RFONE_DEV_JOURNAL_DOCUMENT_DIR"
S3_PREFIX = "dev-journal/documents/"
_LOCAL_PREFIX = "local:"
_KEY_RE = re.compile(r"^[0-9a-f]{32}$")


class StorageNotConfiguredError(RuntimeError):
    """No persistent document store is configured for this process."""


class LocalDocumentStore:
    kind = "LOCAL"

    def __init__(self, directory: str | os.PathLike):
        self.directory = Path(directory).resolve()

    def put(self, data: bytes) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        key = uuid.uuid4().hex
        (self.directory / key).write_bytes(data)
        return f"{_LOCAL_PREFIX}{key}"

    def _path(self, storage_path: str | None) -> Path | None:
        if not storage_path or not storage_path.startswith(_LOCAL_PREFIX):
            return None
        key = storage_path[len(_LOCAL_PREFIX):]
        return self.directory / key if _KEY_RE.match(key) else None

    def read(self, storage_path: str) -> bytes | None:
        path = self._path(storage_path)
        return path.read_bytes() if path is not None and path.is_file() else None

    def discard(self, storage_path: str) -> None:
        path = self._path(storage_path)
        if path is not None and path.is_file():
            path.unlink()


class S3DocumentStore:
    kind = "S3"

    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        if client is None:
            import boto3
            client = boto3.client("s3")
        self.client = client

    def put(self, data: bytes) -> str:
        key = f"{S3_PREFIX}{uuid.uuid4().hex}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        return f"s3://{self.bucket}/{key}"

    def _key(self, storage_path: str | None) -> str | None:
        prefix = f"s3://{self.bucket}/{S3_PREFIX}"
        if not storage_path or not storage_path.startswith(prefix):
            return None
        return storage_path[len(f"s3://{self.bucket}/"):] if _KEY_RE.match(storage_path[len(prefix):]) else None

    def read(self, storage_path: str) -> bytes | None:
        key = self._key(storage_path)
        if not key:
            return None
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception:
            return None

    def discard(self, storage_path: str) -> None:
        """Only for a file stored a moment ago whose database row was then
        not saved — never for a document the journal already records."""
        key = self._key(storage_path)
        if key:
            self.client.delete_object(Bucket=self.bucket, Key=key)


def from_environment():
    """The configured store; raises `StorageNotConfiguredError` when none is."""
    bucket = (os.environ.get(BUCKET_ENV_VAR) or "").strip()
    if bucket:
        return S3DocumentStore(bucket)
    directory = (os.environ.get(DIR_ENV_VAR) or "").strip()
    if directory:
        return LocalDocumentStore(directory)
    raise StorageNotConfiguredError(
        f"Document storage is not configured: set {BUCKET_ENV_VAR} (private S3 bucket) on AWS, "
        f"or {DIR_ENV_VAR} (a persistent local folder) for local development."
    )
