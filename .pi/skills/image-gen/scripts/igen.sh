#!/bin/bash
# igen.sh —— 云端 GPU 生图助手（image-gen skill 的核心脚本）
# 可移植：自动定位项目根（支持仓库内 .pi/skills/ 与全局 ~/.agents/skills/ 两种位置）
#
# 用法：
#   igen status                          # 验证隧道 + 后端状态
#   igen generate --model qwen-image --prompt "一只猫" [--steps 12 --cfg 1.0 --width 1024 --height 1024] [-o 输出.png]
#   igen view <图片.png>                  # 看图（有 deepseek-vision 用视觉模型，否则提示直接 read）
set -uo pipefail

# ---- 定位项目根（两种位置都兼容）----
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT=""
# 1) 仓库内：从 skill 目录向上找 git 根
for d in "$SKILL_DIR" "$SKILL_DIR/.." "$SKILL_DIR/../.." "$SKILL_DIR/../../.."; do
  if root="$(git -C "$d" rev-parse --show-toplevel 2>/dev/null)"; then
    PROJECT_ROOT="$root"; break
  fi
done
# 2) 全局位置回退：常见默认路径
if [ -z "$PROJECT_ROOT" ] && [ -d "$HOME/github-repo/image-gen-studio" ]; then
  PROJECT_ROOT="$HOME/github-repo/image-gen-studio"
fi
if [ -z "$PROJECT_ROOT" ]; then
  echo "错误：找不到 image-gen-studio 项目根（git 上层探测失败）。" >&2
  echo "可设置环境变量 IGEN_PROJECT_ROOT 指定项目路径。" >&2
  exit 1
fi

CLIENT="$PROJECT_ROOT/client/client.py"
ENV_FILE="$PROJECT_ROOT/.env"

# ---- 加载 .env（不覆盖已存在的环境变量）----
if [ -f "$ENV_FILE" ]; then
  while IFS='=' read -r key val; do
    key="$(echo "$key" | tr -d ' ')"
    case "$key" in
      ""|\#*) continue ;;
    esac
    if [ -z "${!key:-}" ]; then
      val="$(echo "$val" | tr -d '"' | tr -d "'")"
      export "$key=$val"
    fi
  done < <(grep -v '^#' "$ENV_FILE")
fi
API_BASE="${API_BASE:-http://localhost:8080}"
API_USER="${API_USER:-comfy}"

status() {
  local out
  out="$(curl -s --max-time 5 -u "$API_USER:$API_PASSWORD" "$API_BASE/status" 2>/dev/null)"
  if ! echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('comfyui',{}).get('status')=='ok' else 1)" 2>/dev/null; then
    echo "✗ 后端不可达。可能原因：SSH 隧道未建立 / ComfyUI 未启动 / .env 未配置"
    echo "  重建隧道：sshpass -p \"\$SSH_PASSWORD\" ssh -fN -o ExitOnForwardFailure=yes -p \"\$SSH_PORT\" -L 8080:localhost:8080 \"\$SSH_USER@\$SERVER_HOST\""
    return 1
  fi
  echo "$out" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print(f\"✓ 后端 OK | GPU: {d['gpu'].get('name','?')} | 队列: {d['queue']['running']}跑/{d['queue']['pending']}等 | ComfyUI: {d['comfyui']['status']}\")"
}

generate() {
  local model="qwen-image" prompt="" steps="" cfg="" width="" height="" out=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --model) model="$2"; shift 2 ;;
      --prompt) prompt="$2"; shift 2 ;;
      --steps) steps="$2"; shift 2 ;;
      --cfg) cfg="$2"; shift 2 ;;
      --width) width="$2"; shift 2 ;;
      --height) height="$2"; shift 2 ;;
      -o) out="$2"; shift 2 ;;
      *) echo "未知参数: $1" >&2; return 1 ;;
    esac
  done
  [ -n "$prompt" ] || { echo "错误：--prompt 必填" >&2; return 1; }
  [ -n "$out" ] || out="/tmp/igen_$(date +%s).png"

  local args=(generate --model "$model" --prompt "$prompt" --wait -o "$out")
  # 按模型填最佳参数（未显式指定时）
  if [ "$model" = "qwen-image" ]; then
    [ -n "$steps" ] && args+=(--steps "$steps") || args+=(--steps 12)
    [ -n "$cfg" ] && args+=(--cfg "$cfg") || args+=(--cfg 1.0)
  elif [ "$model" = "flux" ]; then
    [ -n "$steps" ] && args+=(--steps "$steps") || args+=(--steps 20)
    [ -n "$cfg" ] && args+=(--cfg "$cfg") || args+=(--cfg 1.0)
  else
    [ -n "$steps" ] && args+=(--steps "$steps")
    [ -n "$cfg" ] && args+=(--cfg "$cfg")
  fi
  [ -n "$width" ] && args+=(--width "$width")
  [ -n "$height" ] && args+=(--height "$height")

  echo "▶ 生图中（${model}）：${prompt}"
  python3 "$CLIENT" "${args[@]}" 2>&1
  local rc=$?
  [ $rc -eq 0 ] && [ -f "$out" ] && echo "✅ 已保存: $out"
  return $rc
}

view() {
  local img="${1:-}"
  [ -n "$img" ] && [ -f "$img" ] || { echo "用法: igen view <图片.png>" >&2; return 1; }
  # 优先用 deepseek-vision（全局 skill），否则提示直接 read
  if [ -f "$HOME/.agents/skills/deepseek-vision/scripts/vision.js" ]; then
    node "$HOME/.agents/skills/deepseek-vision/scripts/vision.js" "$img" "描述这张图片的内容" 2>&1
  elif [ -f "$HOME/.pi/agent/skills/deepseek-vision/scripts/vision.js" ]; then
    node "$HOME/.pi/agent/skills/deepseek-vision/scripts/vision.js" "$img" "描述这张图片的内容" 2>&1
  else
    echo "（未找到 deepseek-vision，请用 read 直接查看：read $img）"
  fi
}

case "${1:-}" in
  status) status ;;
  generate) shift; generate "$@" ;;
  view) view "${2:-}" ;;
  *) echo "用法: $0 {status|generate|view}"; exit 1 ;;
esac
