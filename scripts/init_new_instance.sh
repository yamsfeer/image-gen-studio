#!/bin/bash
# 新 4090 实例初始化（阶段一）：服务层依赖 + nginx + Basic Auth
set -e
PY=/root/miniconda3/bin/python

echo "[1/5] 安装服务层依赖 (fastapi/uvicorn/websockets)"
$PY -m pip install -q fastapi uvicorn websockets 2>&1 | tail -1 || true
$PY -c "import fastapi, uvicorn, websockets; print('  依赖 OK:', 'fastapi', fastapi.__version__, 'uvicorn', uvicorn.__version__)"

echo "[2/5] 安装 nginx"
if ! which nginx >/dev/null 2>&1; then
  apt-get update -qq 2>&1 | tail -1
  apt-get install -y -qq nginx apache2-utils 2>&1 | tail -1
fi
nginx -v 2>&1

echo "[3/5] 配置 Basic Auth (comfy / 沿用原密码)"
htpasswd -bc /etc/nginx/.htpasswd comfy 'ofq2znDbcjEHY3'
echo "  htpasswd OK"

echo "[4/5] 写 nginx 反代配置 (8080 -> 8190)"
cat > /etc/nginx/conf.d/comfy.conf <<'EOF'
server {
    listen 0.0.0.0:8080;
    server_name _;
    client_max_body_size 0;

    auth_basic "ComfyUI Image API";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8190;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
EOF

echo "[5/5] 启动 nginx"
nginx -t 2>&1
nginx 2>&1 || systemctl start nginx 2>&1 || service nginx start 2>&1 || true
sleep 1
ss -tlnp 2>/dev/null | grep 8080 || echo "  (8080 待 8190 就绪后可用)"
echo "=== 初始化完成 ==="
