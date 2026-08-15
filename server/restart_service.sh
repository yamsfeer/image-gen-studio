#!/bin/bash
# 重启服务层（uvicorn）。注意：不能直接 pkill 匹配 "uvicorn service:app" 字面串，
# 否则会匹配到执行本脚本的 bash 自身命令行。本脚本作为文件执行，命令行只有 "bash restart_service.sh"，安全。
set -e
PY=/root/miniconda3/bin/python
cd "$(dirname "$0")"

# 杀旧进程（匹配模式不含字面 uvicorn，见顶部注释）
pkill -f '[u]vicorn service:app' 2>/dev/null || true
sleep 2

# 后台启动（AutoDL 无 systemd，必须 setsid nohup + stdin 重定向）
setsid nohup "$PY" -m uvicorn service:app --host 127.0.0.1 --port 8190 > server.log 2>&1 < /dev/null &
sleep 3

# 验证
curl -s --max-time 5 -o /dev/null -w "服务层 HTTP %{http_code}\n" http://127.0.0.1:8190/ || echo "服务层启动失败，看 server.log"
