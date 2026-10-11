"""
storage/object_store.py (Phase 2)
Object-storage abstraction for workspace document bytes.

  - LocalBackend (default): files under the existing workspace upload root.
    The legacy UploadFile endpoints keep using it unchanged.
  - S3Backend (R2/S3): boto3 with endpoint_url (R2) — presigned PUT/GET so
    browsers talk to storage directly and FastAPI never proxies bytes.

Only activate S3 when settings.use_s3_storage is True (S3_BUCKET set).
All boto3 calls are blocking — callers must wrap them in asyncio.to_thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.logging import get_logger

log = get_logger(__name__)

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
}


def content_type_for(filename: str) -> str:
    return CONTENT_TYPES.get(Path(filename or "").suffix.lower(), "application/octet-stream")


def build_object_key(workspace_id: str, doc_id: str, filename: str, prefix: str) -> str:
    """R2/S3 key: <prefix>/workspaces/<ws>/<doc>_<safe name> (no leading slash)."""
    safe = Path(filename or "upload").name.replace("/", "_")
    clean_prefix = (prefix or "").strip().strip("/")
    parts = [p for p in (clean_prefix, "workspaces", workspace_id, f"{doc_id}_{safe}") if p]
    return "/".join(parts)


@dataclass
class ObjectHead:
    key: str
    size_bytes: int
    etag: Optional[str] = None
    content_type: Optional[str] = None


class StorageBackend:
    """Interface both backends implement."""

    name = "base"

    def put_object(self, key: str, data: bytes, content_type: str = "") -> None:
        raise NotImplementedError

    def get_object(self, key: str) -> bytes:
        raise NotImplementedError

    def head_object(self, key: str) -> Optional[ObjectHead]:
        raise NotImplementedError

    def delete_object(self, key: str) -> bool:
        """True when something was deleted (or already absent)."""
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> int:
        """Delete all keys under prefix. Returns deleted count."""
        raise NotImplementedError

    def presigned_put(self, key: str, content_type: str = "", expires: int = 900) -> str:
        raise NotImplementedError

    def presigned_get(self, key: str, expires: int = 900) -> str:
        raise NotImplementedError


class LocalBackend(StorageBackend):
    """Filesystem backend rooted at the workspace upload dir (dev default)."""

    name = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        # Keys are relative; guard against traversal.
        rel = (key or "").lstrip("/").replace("..", "_")
        return self.root / rel

    def put_object(self, key: str, data: bytes, content_type: str = "") -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get_object(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def head_object(self, key: str) -> Optional[ObjectHead]:
        p = self._path(key)
        if not p.is_file():
            return None
        return ObjectHead(key=key, size_bytes=p.stat().st_size)

    def delete_object(self, key: str) -> bool:
        try:
            self._path(key).unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            log.warning("Local delete failed", key=key, error=str(exc))
            return False

    def delete_prefix(self, prefix: str) -> int:
        base = self._path(prefix.strip("/"))
        if not base.exists():
            return 0
        count = 0
        if base.is_file():
            base.unlink()
            return 1
        for f in sorted(base.rglob("*")):
            if f.is_file():
                try:
                    f.unlink()
                    count += 1
                except OSError:
                    pass
        return count

    def presigned_put(self, key: str, content_type: str = "", expires: int = 900) -> str:
        raise NotImplementedError("Local backend has no presigned URLs (use direct upload)")

    def presigned_get(self, key: str, expires: int = 900) -> str:
        raise NotImplementedError("Local backend has no presigned URLs (files are on local disk)")


class S3Backend(StorageBackend):
    """R2/S3 backend via boto3 (S3-compatible API covers R2 with endpoint_url)."""

    name = "s3"

    def __init__(
        self,
        bucket: str,
        endpoint_url: str = "",
        region: str = "auto",
        access_key: str = "",
        secret_key: str = "",
    ):
        self.bucket = bucket
        self.endpoint_url = endpoint_url or None
        self.region = region or "auto"
        self.access_key = access_key
        self.secret_key = secret_key
        self._client = None

    def _client_or_raise(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is not installed") from exc
        kwargs: dict = {"region_name": self.region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.access_key:
            kwargs["aws_access_key_id"] = self.access_key
        if self.secret_key:
            kwargs["aws_secret_access_key"] = self.secret_key
        self._client = boto3.client("s3", **kwargs)
        return self._client

    def put_object(self, key: str, data: bytes, content_type: str = "") -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client_or_raise().put_object(
            Bucket=self.bucket, Key=key, Body=data, **extra
        )

    def get_object(self, key: str) -> bytes:
        resp = self._client_or_raise().get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def head_object(self, key: str) -> Optional[ObjectHead]:
        try:
            resp = self._client_or_raise().head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return ObjectHead(
            key=key,
            size_bytes=int(resp.get("ContentLength", 0)),
            etag=(resp.get("ETag") or "").strip('"') or None,
            content_type=resp.get("ContentType"),
        )

    def delete_object(self, key: str) -> bool:
        try:
            self._client_or_raise().delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            log.warning("S3 delete failed", key=key, error=str(exc))
            return False

    def delete_prefix(self, prefix: str) -> int:
        client = self._client_or_raise()
        clean = prefix.strip("/")
        count = 0
        token = None
        while True:
            kwargs: dict = {"Bucket": self.bucket, "Prefix": clean}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                client.delete_object(Bucket=self.bucket, Key=obj["Key"])
                count += 1
            token = resp.get("NextContinuationToken")
            if not token:
                break
        return count

    def presigned_put(self, key: str, content_type: str = "", expires: int = 900) -> str:
        params: dict = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return self._client_or_raise().generate_presigned_url(
            "put_object", Params=params, ExpiresIn=expires
        )

    def presigned_get(self, key: str, expires: int = 900) -> str:
        return self._client_or_raise().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )


_cached: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Process-wide backend singleton (local default, S3 when configured)."""
    global _cached
    if _cached is not None:
        return _cached
    # Import here so tests can monkeypatch settings before first use.
    from ..core.config import settings

    if settings.use_s3_storage:
        _cached = S3Backend(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
        )
        log.info("Object storage: S3/R2", bucket=settings.s3_bucket)
    else:
        _cached = LocalBackend(settings.workspace_upload_path)
        log.info("Object storage: local disk")
    return _cached


def reset_storage_cache() -> None:
    """Drop the singleton (tests switch backends between cases)."""
    global _cached
    _cached = None
