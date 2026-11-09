#!/usr/bin/env bash
# One-time setup: the skill's own Python environment (.venv) and the Outfit preview font.
#   bash scripts/setup.sh            then use .venv/bin/python for every script
# Maintenance scripts (maintenance/) also need fontTools: .venv/bin/python -m pip install fonttools
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv "$ROOT/.venv" 2>/dev/null || python3 -m venv --without-pip "$ROOT/.venv"
fi
"$ROOT/.venv/bin/python" -m pip --version >/dev/null 2>&1 || curl -sS https://bootstrap.pypa.io/get-pip.py | "$ROOT/.venv/bin/python"
"$ROOT/.venv/bin/python" -m pip install -q -r "$ROOT/requirements.txt"
# Outfit stands in for the licensed Mark Pro in previews only (OFL, assets/fonts/OFL-Outfit.txt); decks never embed it
mkdir -p "$HOME/.local/share/fonts/outfit"
cp "$ROOT/assets/fonts/Outfit.ttf" "$ROOT/assets/fonts/OFL-Outfit.txt" "$HOME/.local/share/fonts/outfit/"
fc-cache -f "$HOME/.local/share/fonts" >/dev/null 2>&1 || true
command -v soffice >/dev/null || echo "note: LibreOffice (soffice) is needed for PDF and slide renders"
command -v pdftoppm >/dev/null || echo "note: poppler-utils (pdftoppm) is needed for slide images"
"$ROOT/.venv/bin/python" -c "import pptx, lxml, PIL, numpy" && echo "ready: $ROOT/.venv/bin/python"
