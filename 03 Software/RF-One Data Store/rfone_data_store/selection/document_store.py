"""Where Selection keeps original résumé documents (SELECTION_AWS_PUBLISH_001).

Two stores, chosen by configuration, with the same small interface:

- LOCAL (default, development): the file stays in the app's own `uploads/`
  folder, exactly as before. `storage_path` is the local path.
- S3 (deployment): `RFONE_SELECTION_DOCUMENT_BUCKET` names a private bucket;
  each document is stored once under `selection/resumes/<uuid>/<name>` and
  `storage_path` is `s3://<bucket>/<key>`. The service's disk is only a
  temporary place to read the text from, never the archive, so documents
  survive restarts and new deployments. Documents are never public: the app
  reads them and serves them itself, behind the RF-One login.

The original file name always stays in `RawResume.original_filename`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass

from werkzeug.utils import secure_filename

BUCKET_ENV_VAR = "RFONE_SELECTION_DOCUMENT_BUCKET"
S3_PREFIX = "selection/resumes/"


@dataclass
class StagedUpload:
    """A just-uploaded file: `local_path` is readable now (for text
    extraction); `storage_path` is what gets recorded; `cleanup()` removes
    any temporary copy."""

    local_path: str
    storage_path: str
    temporary_dir: str | None = None

    def cleanup(self) -> None:
        if self.temporary_dir:
            shutil.rmtree(self.temporary_dir, ignore_errors=True)


class LocalDocumentStore:
    kind = "LOCAL"

    def __init__(self, upload_dir: str):
        self.upload_dir = os.path.normpath(upload_dir)

    def stage(self, file_storage, filename: str) -> StagedUpload:
        path = os.path.join(self.upload_dir, f"{uuid.uuid4().hex[:8]}_{filename}")
        file_storage.save(path)
        return StagedUpload(local_path=path, storage_path=path)

    def discard(self, storage_path: str) -> None:
        """Local files are kept, as before this store existed."""

    def _inside(self, storage_path: str | None) -> str | None:
        if not storage_path:
            return None
        path = os.path.normpath(storage_path)
        try:
            inside = os.path.commonpath([path, self.upload_dir]) == self.upload_dir
        except ValueError:
            return None
        return path if inside else None

    def exists(self, storage_path: str | None) -> bool:
        path = self._inside(storage_path)
        return bool(path and os.path.isfile(path))

    def read(self, storage_path: str) -> bytes | None:
        path = self._inside(storage_path)
        if not path or not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            return handle.read()


class S3DocumentStore:
    kind = "S3"

    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        if client is None:
            import boto3
            client = boto3.client("s3")
        self.client = client

    def _key(self, storage_path: str | None) -> str | None:
        prefix = f"s3://{self.bucket}/"
        if not storage_path or not storage_path.startswith(prefix):
            return None
        key = storage_path[len(prefix):]
        return key if key.startswith(S3_PREFIX) else None

    def stage(self, file_storage, filename: str) -> StagedUpload:
        temporary_dir = tempfile.mkdtemp(prefix="selection_upload_")
        local_path = os.path.join(temporary_dir, secure_filename(filename) or "resume")
        file_storage.save(local_path)
        key = f"{S3_PREFIX}{uuid.uuid4().hex}/{secure_filename(filename) or 'resume'}"
        try:
            self.client.upload_file(local_path, self.bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise
        return StagedUpload(local_path=local_path, storage_path=f"s3://{self.bucket}/{key}",
                            temporary_dir=temporary_dir)

    def discard(self, storage_path: str) -> None:
        """Removes a document that was stored but not kept (a duplicate or a
        failed import), so nothing is left without a record pointing to it."""
        key = self._key(storage_path)
        if key:
            self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, storage_path: str | None) -> bool:
        key = self._key(storage_path)
        if not key:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def read(self, storage_path: str) -> bytes | None:
        key = self._key(storage_path)
        if not key:
            return None
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception:
            return None


def from_environment(upload_dir: str):
    bucket = (os.environ.get(BUCKET_ENV_VAR) or "").strip()
    return S3DocumentStore(bucket) if bucket else LocalDocumentStore(upload_dir)
