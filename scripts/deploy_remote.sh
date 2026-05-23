#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/Health-Rag-Assistant}"
BRANCH="${BRANCH:-main}"

echo "[deploy] app_dir=${APP_DIR} branch=${BRANCH}"

if [ ! -d "${APP_DIR}/.git" ]; then
  echo "[deploy] repo not found, cloning..."
  git clone -b "${BRANCH}" https://github.com/yuanguihuafang/Health-Rag-Assistant "${APP_DIR}"
fi

cd "${APP_DIR}"

echo "[deploy] fetching latest code..."
git fetch --all --prune
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

if [ ! -f backend/.env ]; then
  echo "[deploy] backend/.env missing, create from example first"
  cp backend/.env.example backend/.env
  echo "[deploy] please edit backend/.env then redeploy"
  exit 2
fi

echo "[deploy] docker compose build + up..."
docker compose up -d --build

echo "[deploy] health check..."
sleep 5
if command -v curl >/dev/null 2>&1; then
  curl -fsS "http://127.0.0.1:8000/api/health-rag/health/" || true
fi

echo "[deploy] done"
