#!/usr/bin/env bash
# Starts the Django dev server on the port declared in .env (BACKEND_PORT),
# so the backend port is only ever configured in one place. Falls back to
# 8000 if .env is missing or doesn't set it (matches backend/config/settings.py).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"

exec uv run backend/manage.py runserver "0.0.0.0:${BACKEND_PORT}"
