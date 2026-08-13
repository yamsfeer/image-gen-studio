#!/bin/bash
# deploy.sh —— 把本地 code/server/ 同步到云端服务器并重启服务层
#
# 用法：./deploy.sh
# 配置：项目根目录 .env（复制 .env.example 填写），或用同名环境变量覆盖。
# 前置：本机可 SSH 到服务器（密码登录需装 sshpass）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
LOCAL_DIR="$SCRIPT_DIR/code/server"

# ---- 加载 .env（存在才加载；已导出的环境变量优先于 .env）----
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  echo "⚠️  未找到 $ENV_FILE，将使用环境变量或默认值。"
  echo "   建议先执行：cp .env.example .env 并填写真实值。"
fi

# ---- 必需变量（来自 .env 或环境变量）----
SERVER_HOST="${SERVER_HOST:?缺少 SERVER_HOST，请配置 .env}"
SSH_PORT="${SSH_PORT:?缺少 SSH_PORT，请配置 .env}"
SSH_USER="${SSH_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/root/image-service}"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/bin/python}"

SERVER="${SSH_USER}@${SERVER_HOST}"

# ---- SSH / rsync 命令（有 sshpass 且给了密码就用密码，否则用 SSH key）----
SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=no)
if command -v sshpass >/dev/null 2>&1 && [ -n "${SSH_PASSWORD:-}" ]; then
  RSYNC_RSH="sshpass -p $SSH_PASSWORD ssh ${SSH_OPTS[*]}"
  SSH_CMD=(sshpass -p "$SSH_PASSWORD" ssh "${SSH_OPTS[@]}")
else
  RSYNC_RSH="ssh ${SSH_OPTS[*]}"
  SSH_CMD=(ssh "${SSH_OPTS[@]}")
fi

echo "[1/3] 同步 code/server/ → $SERVER:$REMOTE_DIR"
rsync -az --delete -e "$RSYNC_RSH" "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

echo "[2/3] 重启服务层（uvicorn）"
"${SSH_CMD[@]}" "$SERVER" "pkill -f '[u]vicorn service:app' 2>/dev/null || true; sleep 2; \
  ( cd $REMOTE_DIR && setsid nohup $PYTHON_BIN \
    -m uvicorn service:app --host 127.0.0.1 --port 8190 \
    > server.log 2>&1 < /dev/null & )"

echo "[3/3] 验证"
sleep 3
"${SSH_CMD[@]}" "$SERVER" "curl -s --max-time 5 -o /dev/null -w '服务层 HTTP %{http_code}\n' http://127.0.0.1:8190/stats"
echo "完成。前端（webui 或浏览器）刷新即可看到新后端效果。"
