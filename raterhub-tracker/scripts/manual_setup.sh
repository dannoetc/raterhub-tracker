#!/usr/bin/env bash
set -euo pipefail

# This script bootstraps a local (non-Docker) install with a Python virtualenv.
# It creates a .env file if one does not exist and installs all dependencies.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
VENV_DIR="${APP_DIR}/.venv"
ENV_FILE="${ROOT_DIR}/.env"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to set up the environment." >&2
  exit 1
fi

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${ROOT_DIR}/requirements.txt"

if [ ! -f "${ENV_FILE}" ]; then
  cat <<'ENV_VARS' > "${ENV_FILE}"
SECRET_KEY=change-me
DATABASE_URL=sqlite:///./app.db
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ALLOWED_ORIGINS=https://www.raterhub.com,https://api.raterhub.com
DEBUG=false
ENV_VARS
  echo "Created ${ENV_FILE} with default values. Please review before running the app."
else
  echo "Using existing ${ENV_FILE}."
fi

echo "\nSetup complete. To start the app locally:"
echo "  source ${VENV_DIR}/bin/activate"
echo "  cd ${APP_DIR}"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
