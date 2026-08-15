#!/bin/bash
# autorecover.sh —— 服务自愈 + 开机自启脚本
#
# 职责：检查 ComfyUI / 服务层 / nginx 三个服务，没跑就拉起（幂等，可反复执行）。
# 用法：
#   手动：bash scripts/autorecover.sh
#   开机自启：内容被 /etc/autodl.sh 引用（AutoDL 每次开机自动执行，见 docs/server-status.md）
#
# 注意：不碰 27B（llama-server）—— 那是另一个 AI 进程管理的，避免冲突。
set -u

PY=/root/miniconda3/bin/python
COMFY_DIR=/root/autodl-tmp/ComfyUI
SERVICE_DIR=/root/image-service
LOG=/tmp/autorecover.log

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# ---- 1. ComfyUI（:8188，显卡）----
if [ -z "$(pgrep -f '[m]ain.py --listen')" ]; then
  log "ComfyUI 未运行，拉起..."
  cd "$COMFY_DIR" 2>/dev/null || { log "错误：$COMFY_DIR 不存在"; }
  if [ -f "$COMFY_DIR/main.py" ]; then
    setsid nohup "$PY" main.py --listen 127.0.0.1 --port 8188 \
      > /root/comfyui_service.log 2>&1 < /dev/null &
    log "ComfyUI 已启动"
  fi
else
  log "ComfyUI 运行中"
fi

# ---- 2. 服务层（:8190，FastAPI）----
if [ -z "$(pgrep -f '[u]vicorn service:app')" ]; then
  log "服务层未运行，拉起..."
  cd "$SERVICE_DIR" 2>/dev/null || { log "错误：$SERVICE_DIR 不存在"; }
  if [ -f "$SERVICE_DIR/service.py" ]; then
    setsid nohup "$PY" -m uvicorn service:app --host 127.0.0.1 --port 8190 \
      > "$SERVICE_DIR/server.log" 2>&1 < /dev/null &
    log "服务层已启动"
  fi
else
  log "服务层运行中"
fi

# ---- 3. nginx（:8080 反代）----
if [ -z "$(pgrep -f '[n]ginx: master')" ]; then
  log "nginx 未运行，启动..."
  nginx 2>/dev/null && log "nginx 已启动" || log "nginx 启动失败"
else
  log "nginx 运行中"
fi

# 等 30 秒让 ComfyUI 完成加载（模型常驻，首次加载慢）
sleep 30
# 最终状态
echo "autorecover 完成: ComfyUI=$(pgrep -cf '[m]ain.py --listen' 2>/dev/null || echo 0) \
服务层=$(pgrep -cf '[u]vicorn service:app' 2>/dev/null || echo 0) \
nginx=$(pgrep -cf '[n]ginx: master' 2>/dev/null || echo 0)"
