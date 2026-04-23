#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

cd "${ROOT_DIR}"

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e .

mkdir -p "${ROOT_DIR}/data" "${ROOT_DIR}/logs"

if [[ ! -f "${ROOT_DIR}/config/local.yaml" ]]; then
  cp "${ROOT_DIR}/config/local.example.yaml" "${ROOT_DIR}/config/local.yaml"
fi

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
fi

python "${ROOT_DIR}/scripts/init_db.py"

echo "Bootstrap complete."
echo "Edit ${ROOT_DIR}/.env and ${ROOT_DIR}/config/local.yaml before enabling systemd services."
