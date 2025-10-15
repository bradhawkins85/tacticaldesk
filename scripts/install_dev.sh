#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env.dev}"
STATE_DIR="/etc/tacticaldesk"
SERVICE_NAME="${TACTICAL_DESK_DEV_SERVICE_NAME:-tacticaldesk-dev}"
APP_DIR="${TACTICAL_DESK_DEV_APP_DIR:-/opt/tacticaldesk-dev}"
BRANCH="${TACTICAL_DESK_REPO_BRANCH:-main}"
PYTHON_BIN="${TACTICAL_DESK_PYTHON_BIN:-python3}"
PORT="${TACTICAL_DESK_DEV_PORT:-8001}"
DEV_DB_URL="${TACTICAL_DESK_DEV_DATABASE_URL:-sqlite+aiosqlite:///./tacticaldesk_dev.db}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

REPO_URL="${TACTICAL_DESK_REPO_URL:-https://github.com/example/tacticaldesk.git}"
GIT_USERNAME="${TACTICAL_DESK_GIT_USERNAME:-}"
GIT_TOKEN="${TACTICAL_DESK_GIT_TOKEN:-}"

if [[ -n "${GIT_USERNAME}" && -n "${GIT_TOKEN}" ]]; then
  AUTH_REPO_URL="${REPO_URL/https:\/\//https://${GIT_USERNAME}:${GIT_TOKEN}@}"
else
  AUTH_REPO_URL="${REPO_URL}"
fi

sudo mkdir -p "${APP_DIR}" "${STATE_DIR}"
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
TEMP_FILE="$(mktemp)"
grep -Ev '^(DATABASE_URL|TACTICAL_DESK_ENABLE_INSTALLERS)=' "${SERVICE_ENV_FILE}" > "${TEMP_FILE}" || true
cat "${TEMP_FILE}" > "${SERVICE_ENV_FILE}"
rm -f "${TEMP_FILE}"
{
  echo "DATABASE_URL=${DEV_DB_URL}";
  echo "TACTICAL_DESK_ENABLE_INSTALLERS=0";
} >> "${SERVICE_ENV_FILE}"

"${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
# shellcheck disable=SC1091
source "${APP_DIR}/.venv/bin/activate"
pip install --upgrade pip
pip install --no-cache-dir -r "${APP_DIR}/requirements.txt"

deactivate

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
cat <<SERVICE | sudo tee "${SERVICE_FILE}" > /dev/null
[Unit]
Description=Tactical Desk Development Service (${SERVICE_NAME})
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${APP_DIR}
EnvironmentFile=${SERVICE_ENV_FILE}
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo "${SERVICE_NAME} deployed to ${APP_DIR} on port ${PORT} using ${DEV_DB_URL}."
