"""Shared fixtures. Every test here hits the real Neon database (in a throwaway schema, dropped at
teardown) and the real Blob store (under a run-unique 'test/<token>/' prefix, cleaned up at teardown, so
concurrent test runs never collide). Nothing is mocked.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx2
import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))


def _load_env_local() -> None:
    """`set -a; . .env.local; set +a` for whoever runs pytest without having done that themselves."""
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env_local()

from app import blobs, config, jobs  # noqa: E402


def _with_search_path(dsn: str, schema: str) -> str:
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query))
    q["options"] = f"-c search_path={schema},public"
    # libpq's URI parser wants %20 for a space, not the form-encoded "+" urlencode() uses by default.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, quote_via=quote), parts.fragment))


@pytest.fixture
def pg_schema():
    """A fresh schema `test_<random>` on the real database; config.DATABASE_URL points new connections at
    it (via libpq's `options=-c search_path=...`) for the test's duration.

    Neon's pooled endpoint (pgbouncer, transaction mode) rejects the `options` startup parameter, so the
    schema override - and this fixture's own admin DDL - use the unpooled connection string instead."""
    admin_dsn = os.environ.get("DATABASE_URL_UNPOOLED") or config.DATABASE_URL
    assert admin_dsn, "DATABASE_URL/DATABASE_URL_UNPOOLED not set (source .env.local first)"
    schema = "test_" + secrets.token_hex(6)
    with psycopg.connect(admin_dsn) as conn, conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema}")
    old_dsn = config.DATABASE_URL
    config.DATABASE_URL = _with_search_path(admin_dsn, schema)
    jobs._schema_ready.clear()
    try:
        yield schema
    finally:
        config.DATABASE_URL = old_dsn
        jobs._schema_ready.clear()
        with psycopg.connect(admin_dsn) as conn, conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def blob_cleanup():
    """Deletes every blob under the fixed 'test/' and 'uploads/test/' prefixes after the test. Kept for
    test_worker.py (build-plane), which already depends on it; this agent's own tests use blob_ns/upload_ns
    instead, since a fixed prefix collides when two test runs overlap (see those fixtures below)."""
    yield
    blobs.delete_prefix("test/")
    blobs.delete_prefix("uploads/test/")


@pytest.fixture
def blob_ns():
    """A blob prefix unique to this test run (like pg_schema, but for Blob): concurrent test runs (this
    agent's and the orchestrator's) must not share a pathname, or one run's cleanup deletes the other's
    live blob mid-test. Deliberately NOT under the bare 'test/' prefix: blob_cleanup (above, kept for
    test_worker.py) sweeps all of 'test/' broadly and would still collide with it otherwise."""
    ns = f"testns-{secrets.token_hex(8)}/"
    yield ns
    blobs.delete_prefix(ns)


@pytest.fixture
def upload_ns():
    """Same idea as blob_ns, but under 'uploads/' so it satisfies the API's real client-upload prefix
    check - a genuine upload blob's own path, just scoped under a run-unique segment."""
    ns = f"uploads/test-{secrets.token_hex(8)}/"
    yield ns
    blobs.delete_prefix(ns)


@pytest.fixture
async def client():
    """An HTTP client against the real FastAPI app (vercel's httpx2, an httpx fork, over an ASGI transport:
    no server process, but every route, dependency and middleware runs for real)."""
    from app import main
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=main.app), base_url="http://test") as c:
        yield c
