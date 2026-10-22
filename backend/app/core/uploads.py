"""
core/uploads.py
Bounded, non-buffering upload writes shared by the workspace and legacy routes.

FastAPI/Starlette already spools multipart bodies to a temporary file, but
``await file.read()`` still pulls the whole payload into process memory. These
helpers copy the spooled file in bounded chunks and stop as soon as the
configured cap is crossed. The partial destination is always removed on error,
so a rejected upload cannot leave orphan bytes on disk.
"""
import asyncio
import os
from pathlib import Path

from fastapi import UploadFile

UPLOAD_CHUNK_SIZE = 1024 * 1024


class UploadTooLarge(Exception):
    """Raised when an upload exceeds the configured maximum size."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"File too large (max {max_bytes} bytes)")
        self.max_bytes = max_bytes


async def save_upload_limited(
    upload: UploadFile,
    destination: Path,
    max_bytes: int,
) -> int:
    """
    Copy ``upload`` to ``destination`` in chunks, enforcing ``max_bytes``.

    Returns the number of bytes written. Raises ``UploadTooLarge`` before or
    during the copy when the cap is exceeded. The caller is responsible for
    atomically renaming the destination once this function returns.
    """
    if max_bytes <= 0:
        raise UploadTooLarge(max_bytes)

    known_size = getattr(upload, "size", None)
    if isinstance(known_size, int) and known_size > max_bytes:
        raise UploadTooLarge(max_bytes)

    destination.parent.mkdir(parents=True, exist_ok=True)

    def _copy() -> int:
        total = 0
        # FastAPI leaves the spooled file at position 0, but seek explicitly so
        # the helper is safe if a caller has inspected the stream first.
        upload.file.seek(0)
        with destination.open("wb") as out:
            while True:
                chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLarge(max_bytes)
                out.write(chunk)
        return total

    try:
        return await asyncio.to_thread(_copy)
    except BaseException:
        # Includes cancellation and UploadTooLarge: never leave a partial file.
        destination.unlink(missing_ok=True)
        raise


def atomic_replace(source: Path, destination: Path) -> None:
    """Replace ``destination`` with ``source`` on the same filesystem."""
    os.replace(source, destination)
