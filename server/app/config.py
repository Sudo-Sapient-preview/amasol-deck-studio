"""Paths, model choices and environment settings."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = Path(os.environ.get("DECK_SKILL_DIR", ROOT / "skill")).resolve()
SKILL_PY = Path(os.environ.get("DECK_SKILL_PYTHON", SKILL_DIR / ".venv" / "bin" / "python"))
RUNNER_DIR = ROOT / "server" / "runner"
DATA_DIR = Path(os.environ.get("DECK_DATA_DIR", ROOT / "data")).resolve()
JOBS_DIR = DATA_DIR / "jobs"

# Postgres (Neon; psycopg 3). See Contracts in PLAN.md for the schema.
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Where the worker's code lives inside a sandbox snapshot, and which snapshot to boot it from.
SANDBOX_REPO = Path(os.environ.get("SANDBOX_REPO", "/vercel/sandbox/app"))
DECK_SANDBOX_SNAPSHOT = os.environ.get("DECK_SANDBOX_SNAPSHOT")

# LLM proxy (Anthropic Messages API compatible)
LLM_BASE_URL = os.environ.get("LLM_PROXY_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or "https://llm-proxy.sudosapient.dev"
LLM_API_KEY = os.environ.get("LLM_PROXY_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""

MODELS = [
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "hint": "Best quality"},
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "hint": "Faster"},
]
DEFAULT_MODEL = os.environ.get("DECK_MODEL", "claude-opus-5-5")

# Upload limits
MAX_UPLOAD_BYTES = 200 * 1024 * 1024        # whole request
MAX_FILE_BYTES = 60 * 1024 * 1024           # one file
MAX_FILES = 200
MAX_ZIP_MEMBERS = 500
MAX_ZIP_TOTAL = 300 * 1024 * 1024
INLINE_SOURCE_CHARS = 120_000               # sources up to this size go straight into the prompt
MAX_REFERENCE_IMAGES = 8                    # design-reference images shown to the model

try:  # only the sandboxed worker writes here; the API's filesystem may be read-only
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
