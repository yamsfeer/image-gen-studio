#!/bin/bash
# ============================================================
# setup-server.sh —— 服务器一键重建脚本（幂等，可重跑）
#
# 用途：全新实例从零恢复全部环境：ComfyUI + 插件 + 模型 + nginx + 启动脚本
# 用法（本机执行，把脚本推到服务器再跑）：
#   scp setup/setup-server.sh root@服务器:/root/
#   ssh root@服务器 'bash /root/setup-server.sh'
# 前置：AutoDL 实例已开（root 登录），数据盘有空间（>80G）
#
# 可配置（环境变量，均有 AutoDL 默认值）：
#   PYTHON_BIN  DATA_DIR  COMFY_DIR  REMOTE_DIR  API_USER  API_PASSWORD
# ============================================================
set -e

PY="${PYTHON_BIN:-/root/miniconda3/bin/python}"
DATA="${DATA_DIR:-/root/autodl-tmp}"
COMFY="${COMFY_DIR:-$DATA/ComfyUI}"
REMOTE_DIR="${REMOTE_DIR:-/root/image-service}"
MODELS_CACHE="$DATA/models/models"   # ModelScope 下载缓存

# nginx Basic Auth 账号/密码（密码优先取 API_PASSWORD 环境变量，否则随机生成）
API_USER="${API_USER:-comfy}"
API_PASSWORD="${API_PASSWORD:-}"

echo "===== [1/7] pip 依赖 ====="
$PY -m pip install -q fastapi "uvicorn[standard]" gguf modelscope requests 2>&1 | grep -vE "WARNING" | tail -1 || true

echo "===== [2/7] ComfyUI 本体 ====="
if [ ! -d "$COMFY/.git" ]; then
  git clone https://gitclone.com/github.com/comfyanonymous/ComfyUI.git "$COMFY"
fi
cd "$COMFY" && git pull -q --ff-only 2>/dev/null || true
# ComfyUI 依赖（torch 已由 AutoDL 预装，只装缺失的）
$PY -m pip install -q -r requirements.txt 2>&1 | grep -vE "WARNING|already" | tail -2 || true

echo "===== [3/7] custom_nodes 插件 ====="
mkdir -p "$COMFY/custom_nodes"
# ComfyUI-GGUF（加载 GGUF 模型必需）
if [ ! -d "$COMFY/custom_nodes/ComfyUI-GGUF" ]; then
  ( cd "$COMFY/custom_nodes" && \
    git clone -q --depth 1 https://gitclone.com/github.com/city96/ComfyUI-GGUF.git )
fi
# AnimateDiff（视频动画，可选）
if [ ! -d "$COMFY/custom_nodes/ComfyUI-AnimateDiff-Evolved" ]; then
  ( cd "$COMFY/custom_nodes" && \
    git clone -q --depth 1 https://gitclone.com/github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git ) || true
fi
$PY -m pip install -q gguf 2>&1 | grep -vE "WARNING|already" | tail -1 || true

echo "===== [4/7] 模型下载（ModelScope 为主，已存在则跳过）====="
mkdir -p "$MODELS_CACHE"
dl_ms() { # $1=仓库 $2=文件匹配模式 $3=自定义缓存目录名
  $PY - <<EOF
from modelscope import snapshot_download
snapshot_download("$1", cache_dir="$MODELS_CACHE", allow_file_pattern=["$2"])
print("OK $1")
EOF
}
dl_ms "QuantStack/Qwen-Image-GGUF" "Qwen_Image-Q3_K_M.gguf"
dl_ms "QuantStack/Qwen-Image-GGUF" "VAE/*"
dl_ms "unsloth/Qwen2.5-VL-7B-Instruct-GGUF" "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
dl_ms "Tongyi-MAI/Z-Image-Turbo" "*"
dl_ms "AI-ModelScope/stable-diffusion-v1-5" "*"
dl_ms "AI-ModelScope/stable-diffusion-xl-base-1.0" "*"

echo "===== [5/7] hf-mirror 下载（ModelScope 没有的文件）====="
[ -f "$COMFY/models/unet/z-image-turbo_fp8_scaled.safetensors" ] || \
  curl -sL -o "$COMFY/models/unet/z-image-turbo_fp8_scaled.safetensors" \
  "https://hf-mirror.com/Kijai/Z-Image_comfy_fp8_scaled/resolve/main/z-image-turbo_fp8_scaled_e4m3fn_KJ.safetensors"
[ -f "$COMFY/models/text_encoders/qwen3_4b_iq4_xs.gguf" ] || \
  curl -sL -o "$COMFY/models/text_encoders/qwen3_4b_iq4_xs.gguf" \
  "https://hf-mirror.com/worstplayer/Z-Image_Qwen_3_4b_text_encoder_GGUF/resolve/main/Qwen_3_4b-imatrix-IQ4_XS.gguf"

echo "===== [6/7] 模型软链到 ComfyUI/models ====="
M=$COMFY/models
ln -sfn "$MODELS_CACHE/AI-ModelScope--stable-diffusion-v1-5/snapshots/master" $M/diffusers/sd15
ln -sfn "$MODELS_CACHE/AI-ModelScope--stable-diffusion-xl-base-1.0/snapshots/master" $M/diffusers/sdxl
ln -sfn "$MODELS_CACHE/Tongyi-MAI--Z-Image-Turbo/snapshots/master" $M/diffusers/z-image-turbo
ln -sfn "$MODELS_CACHE/QuantStack--Qwen-Image-GGUF/snapshots/master/Qwen_Image-Q3_K_M.gguf" $M/unet/Qwen_Image-Q3_K_M.gguf
ln -sfn "$MODELS_CACHE/unsloth--Qwen2.5-VL-7B-Instruct-GGUF/snapshots/master/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf" $M/text_encoders/qwen2.5_vl_7b_q4_k_m.gguf
ln -sfn "$MODELS_CACHE/QuantStack--Qwen-Image-GGUF/snapshots/master/VAE/Qwen_Image-VAE.safetensors" $M/vae/qwen_image_vae.safetensors
ln -sfn "$M/diffusers/z-image-turbo/vae/diffusion_pytorch_model.safetensors" $M/vae/z_image_vae.safetensors
# SDXL 单文件 checkpoint（若缓存里有 sdxl_single 则软链，否则提示手动处理）
[ -f "$DATA/models/sdxl_single/models/AI-ModelScope--stable-diffusion-xl-base-1.0/snapshots/master/sd_xl_base_1.0.safetensors" ] && \
  ln -sfn "$DATA/models/sdxl_single/models/AI-ModelScope--stable-diffusion-xl-base-1.0/snapshots/master/sd_xl_base_1.0.safetensors" $M/checkpoints/sd_xl_base_1.0.safetensors || \
  echo "  提示：SDXL 单文件 ckpt 未在缓存，检查 checkpoints/ 目录"

echo "===== [7/7] nginx + 启动脚本 ====="
mkdir -p "$REMOTE_DIR"

# 反代配置：只暴露 FastAPI(8190)；ComfyUI(8188) 由服务层内部直连，不对外
NGINX_CONF=/etc/nginx/conf.d/comfy.conf
if ! grep -q "8190" "$NGINX_CONF" 2>/dev/null; then
  cat > "$NGINX_CONF" <<'NGINX_EOF'
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
NGINX_EOF
fi

# Basic Auth：始终按当前账号/密码刷新（幂等，重跑会同步密码）
if [ -z "$API_PASSWORD" ]; then
  API_PASSWORD="$(openssl rand -base64 12 | tr -d '=+/')"
  echo "⚠️  未提供 API_PASSWORD，已随机生成。请把它填到本地 .env 的 API_PASSWORD："
  echo "     $API_PASSWORD"
fi
htpasswd -cb /etc/nginx/.htpasswd "$API_USER" "$API_PASSWORD"
echo "$API_PASSWORD" > /root/comfy_api_password.txt
chmod 600 /root/comfy_api_password.txt

# 一键启动脚本（幂等；路径可用同名环境变量覆盖）
cat > "$REMOTE_DIR/start_all.sh" <<'START_EOF'
#!/bin/bash
# 一键启动：ComfyUI(8188) + 服务层(8190) + nginx reload（幂等，可重跑）
PY="${PYTHON_BIN:-/root/miniconda3/bin/python}"
DATA="${DATA_DIR:-/root/autodl-tmp}"
COMFY="${COMFY_DIR:-$DATA/ComfyUI}"
SERVICE="${REMOTE_DIR:-/root/image-service}"

cd "$COMFY" || exit 1
[ -z "$(pgrep -f '[m]ain.py --listen')" ] && \
  setsid nohup "$PY" main.py --listen 127.0.0.1 --port 8188 > /root/comfyui_service.log 2>&1 < /dev/null &
sleep 1
cd "$SERVICE" || exit 1
[ -z "$(pgrep -f '[u]vicorn service:app')" ] && \
  setsid nohup "$PY" -m uvicorn service:app --host 127.0.0.1 --port 8190 > server.log 2>&1 < /dev/null &
nginx -s reload 2>/dev/null || true
echo "OK: ComfyUI=$(pgrep -cf '[m]ain.py --listen') 服务层=$(pgrep -cf '[u]vicorn service:app')"
START_EOF
chmod +x "$REMOTE_DIR/start_all.sh"

echo ""
echo "===== 重建完成 ====="
echo "下一步：把服务层代码同步上来并启动"
echo "  本机：./deploy.sh（含同步 code/server/ + 重启 + 验证）"
echo "  或手动：scp code/server/*.py root@服务器:$REMOTE_DIR/ 然后 $REMOTE_DIR/start_all.sh"
