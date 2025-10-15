#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/../.env}"
STATE_DIR="/etc/tacticaldesk"
SERVICE_NAME="${TACTICAL_DESK_SERVICE_NAME:-tacticaldesk}"
APP_DIR="${TACTICAL_DESK_APP_DIR:-/opt/tacticaldesk}"
BRANCH="${TACTICAL_DESK_REPO_BRANCH:-main}"
PYTHON_BIN="${TACTICAL_DESK_PYTHON_BIN:-python3}"

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

if [[ ! -d "${APP_DIR}" ]]; then
  echo "Application directory ${APP_DIR} not found. Run install.sh first." >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "${APP_DIR} does not appear to be a git repository." >&2
  exit 1
fi

if [[ -f "${STATE_DIR}/${SERVICE_NAME}.env" && -f "${ENV_FILE}" ]]; then
  install -m 600 "${ENV_FILE}" "${STATE_DIR}/${SERVICE_NAME}.env"
fi

if [[ -n "${GIT_USERNAME}" && -n "${GIT_TOKEN}" ]]; then
  git -C "${APP_DIR}" remote set-url origin "${AUTH_REPO_URL}"
fi

git -C "${APP_DIR}" fetch origin "${BRANCH}"
git -C "${APP_DIR}" checkout "${BRANCH}"
git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"

"${APP_DIR}/.venv/bin/pip" install --no-cache-dir -r "${APP_DIR}/requirements.txt"

sudo systemctl restart "${SERVICE_NAME}.service"
sudo systemctl status "${SERVICE_NAME}.service" --no-pager

echo "${SERVICE_NAME} updated from ${BRANCH} and service restarted."
