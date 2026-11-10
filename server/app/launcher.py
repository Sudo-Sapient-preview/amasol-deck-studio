"""Create/stop the one sandbox a job runs in. See Contracts (Sandbox) in PLAN.md."""
from __future__ import annotations

import os
import subprocess

from vercel.sandbox import SandboxApiError, SandboxResources, SnapshotSource, create_sandbox, get_sandbox

from . import config

EXEC_TIME_LIMIT = 60 * 60  # 60 min hard backstop


def _name(job_id: str) -> str:
    return f"deck-{job_id}"


def _worker_env() -> dict[str, str]:
    return {
        "DATABASE_URL": config.DATABASE_URL,
        "BLOB_READ_WRITE_TOKEN": os.environ.get("BLOB_READ_WRITE_TOKEN", ""),
        "LLM_PROXY_BASE_URL": config.LLM_BASE_URL,
        "LLM_PROXY_API_KEY": config.LLM_API_KEY,
        "DECK_DATA_DIR": "/vercel/sandbox/data",
    }


async def launch(job_id: str) -> None:
    """Create a sandbox from the code snapshot and start `python -m app.worker <job_id>` detached."""
    sandbox = await create_sandbox(
        name=_name(job_id),
        source=SnapshotSource(snapshot_id=config.DECK_SANDBOX_SNAPSHOT),
        resources=SandboxResources(vcpus=2),
        execution_time_limit=EXEC_TIME_LIMIT,
        persistent=False,
        env=_worker_env(),
    )
    await sandbox.create_command(
        ".venv/bin/python", ["-m", "app.worker", job_id],
        cwd=str(config.SANDBOX_REPO / "server"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


async def stop(job_id: str) -> None:
    """Stop the job's sandbox by name. A sandbox that's already gone is not an error."""
    try:
        sandbox = await get_sandbox(name=_name(job_id))
        await sandbox.stop()
    except SandboxApiError as e:
        if e.status_code != 404:
            raise
