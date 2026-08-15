#!/bin/bash
# 一键启动全套：ComfyUI + 服务层 + nginx（AutoDL 无 systemd，实例重启后手动跑一次）
# 部署在 /root/image-service/start_all.sh（由 deploy.sh rsync 同步）
PY=/root/miniconda3/bin/python

# 1. ComfyUI（显卡，:8188）
cd /root/autodl-tmp/ComfyUI 2>/dev/null || { echo "ComfyUI 目录不存在，先迁移"; exit 1; }
if [ -z "$(pgrep -f '[m]ain.py --listen')" ]; then
  setsid nohup $PY main.py --listen 127.0.0.1 --port 8188 > /root/comfyui_service.log 2>&1 < /dev/null &
fi

# 2. 服务层（:8190）
cd /root/image-service
if [ -z "$(pgrep -f '[u]vicorn service:app')" ]; then
  setsid nohup $PY -m uvicorn service:app --host 127.0.0.1 --port 8190 > server.log 2>&1 < /dev/null &
fi

# 3. nginx reload
nginx -s reload 2>/dev/null || nginx 2>/dev/null || true

sleep 4
echo "OK: ComfyUI=$(pgrep -cf '[m]ain.py --listen') 服务层=$(pgrep -cf '[u]vicorn service:app') nginx=$(pgrep -cf '[n]ginx: master')"
