#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
STATE_DIR="/etc/tacticaldesk"
SERVICE_NAME="${TACTICAL_DESK_SERVICE_NAME:-tacticaldesk}"
APP_DIR="${TACTICAL_DESK_APP_DIR:-/opt/tacticaldesk}"
BRANCH="${TACTICAL_DESK_REPO_BRANCH:-main}"
PYTHON_BIN="${TACTICAL_DESK_PYTHON_BIN:-python3}"
PORT="${TACTICAL_DESK_PORT:-8000}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

ensure_python_dependencies() {
  if command -v "${PYTHON_BIN}" >/dev/null 2>&1 && "${PYTHON_BIN}" -m venv -h >/dev/null 2>&1; then
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm python python-pip
  else
    echo "Unsupported package manager. Install python3 with venv support before continuing." >&2
    exit 1
  fi

  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python interpreter '${PYTHON_BIN}' not found after attempting installation." >&2
    exit 1
  fi

  if ! "${PYTHON_BIN}" -m venv -h >/dev/null 2>&1; then
    echo "The python venv module is unavailable. Please install the python venv package for your distribution." >&2
    exit 1
  fi
}

ensure_python_dependencies

REPO_URL="${TACTICAL_DESK_REPO_URL:-https://github.com/example/tacticaldesk.git}"
GIT_USERNAME="${TACTICAL_DESK_GIT_USERNAME:-}"
GIT_TOKEN="${TACTICAL_DESK_GIT_TOKEN:-}"

if [[ -n "${GIT_USERNAME}" && -n "${GIT_TOKEN}" ]]; then
  AUTH_REPO_URL="${REPO_URL/https:\/\//https://${GIT_USERNAME}:${GIT_TOKEN}@}"
else
  AUTH_REPO_URL="${REPO_URL}"
fi

sudo mkdir -p "${APP_DIR}"
sudo mkdir -p "${STATE_DIR}"
sudo chown "$(whoami)":"$(whoami)" "${APP_DIR}" "${STATE_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  git clone --branch "${BRANCH}" "${AUTH_REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" fetch origin "${BRANCH}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
fi

SERVICE_ENV_FILE="${STATE_DIR}/${SERVICE_NAME}.env"

if [[ -f "${ENV_FILE}" ]]; then
  install -m 600 "${ENV_FILE}" "${SERVICE_ENV_FILE}"
else
  : > "${SERVICE_ENV_FILE}"
  chmod 600 "${SERVICE_ENV_FILE}"
fi

"${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
# shellcheck disable=SC1091
source "${APP_DIR}/.venv/bin/activate"
pip install --upgrade pip
pip install --no-cache-dir -r "${APP_DIR}/requirements.txt"

deactivate

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
cat <<SERVICE | sudo tee "${SERVICE_FILE}" > /dev/null
[Unit]
Description=Tactical Desk Service (${SERVICE_NAME})
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${APP_DIR}
EnvironmentFile=${SERVICE_ENV_FILE}
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo "${SERVICE_NAME} deployed to ${APP_DIR} and listening on port ${PORT}."
