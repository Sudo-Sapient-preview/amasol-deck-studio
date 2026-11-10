"""Private Blob store ("amasol-deck-files"; BLOB_READ_WRITE_TOKEN). See Contracts in PLAN.md.

Layout:
    uploads/<session>/<name>       browser uploads
    jobs/<id>/output/<path>        outputs
    jobs/<id>/state.tar.gz         the work subset follow-ups/retries need

Deletion rule: every blob a job needs survives until that job is deleted. Deleting a job removes jobs/<id>/
and every upload blob no other job's data.uploads references (see jobs.JobStore.upload_blobs_referenced_elsewhere
and main.py's delete_job, which apply the rule).

Synchronous (vercel.blob.sync): the sync API is the SDK's own supported shape for a plain script (the worker),
and from the async API (main.py) every call here is wrapped in starlette's run_in_threadpool, which runs it on
its own thread, away from the event loop and away from the sync SDK's "don't call me from a running loop" rule.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TypeVar

from vercel.blob import sync as blob
from vercel.blob.sync import BlobNotFoundError, HeadResult, PutResult

ACCESS = "private"
T = TypeVar("T")
# Blob content reads can 404 for several seconds after a put, even once head() sees the blob (measured
# 2026-11-10), so every read of a blob we expect to exist retries for ~15 s before giving up.
READ_RETRY_WAITS = (0.5, 1, 2, 3, 4, 5)


def _read(fn: Callable[[], T]) -> T:
    for wait in READ_RETRY_WAITS:
        try:
            return fn()
        except BlobNotFoundError:
            time.sleep(wait)
    return fn()


def put_bytes(pathname: str, data: bytes, *, content_type: str | None = None) -> PutResult:
    return blob.put_blob(pathname, data, access=ACCESS, content_type=content_type, allow_overwrite=True)


def put_file(pathname: str, path: Path, *, content_type: str | None = None) -> PutResult:
    with path.open("rb") as f:
        return blob.put_blob(pathname, f, access=ACCESS, content_length=path.stat().st_size,
                              content_type=content_type, allow_overwrite=True)


@contextmanager
def stream(pathname: str) -> Iterator:
    """Yields chunks of the blob's body; raises BlobNotFoundError if it still doesn't exist after the retries."""
    with ExitStack() as stack:
        yield _read(lambda: stack.enter_context(blob.stream_blob(pathname, access=ACCESS)))


def get_bytes(pathname: str) -> bytes:
    return _read(lambda: blob.get_blob(pathname, access=ACCESS).body)


def head(pathname: str) -> HeadResult | None:
    try:
        return blob.head_blob(pathname)
    except BlobNotFoundError:
        return None


def delete(pathnames: str | list[str]) -> None:
    names = [pathnames] if isinstance(pathnames, str) else list(pathnames)
    for i in range(0, len(names), 1000):  # delete_blob takes at most 1000 pathnames per call
        blob.delete_blob(names[i:i + 1000])


def list_prefix(prefix: str):
    """Every blob under `prefix` (pathname, size, uploaded_at), paginated transparently by the SDK."""
    return blob.query_blobs(prefix=prefix)


def delete_prefix(prefix: str) -> None:
    """Delete every blob whose pathname starts with `prefix`."""
    delete([item.pathname for item in blob.query_blobs(prefix=prefix)])
