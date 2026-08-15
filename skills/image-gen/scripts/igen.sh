#!/bin/bash
# igen.sh —— image-gen skill 的执行脚本
# 职责：读本 skill 目录下的 config.json → 调后端 API 生图/下载。
# 只依赖：curl、python3（解析 JSON）、config.json。
# 不依赖项目路径、client.py、.env —— 全部配置从 config.json 来。
set -uo pipefail

# ---- 定位 config.json（与 SKILL.md 同级）----
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$SKILL_DIR/config.json"

# 先检查 config.json 是否存在（用花括号包裹变量名，避免 set -u 下非 ASCII 字符误解析）
if [ ! -f "${CONFIG}" ]; then
  echo "✗ 未找到 config.json（${CONFIG}）" >&2
  echo "  首次使用需先配置：向用户提问 API 地址/用户名/密码，写入本文件（模板见 config.example.json）" >&2
  exit 1
fi

die() { echo "✗ $*" >&2; exit 1; }
read_config() {
  python3 -c "
import json, sys
try:
    with open('$CONFIG') as f:
        c = json.load(f)
except Exception as e:
    sys.exit(f'config.json 解析失败: {e}')
for k in ['api_base', 'api_user', 'api_password']:
    if not c.get(k):
        sys.exit(f'config.json 缺少字段: {k}')
print(json.dumps(c))
" || exit 1
}
CFG="$(read_config)"
API_BASE="$(echo "$CFG" | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_base"].rstrip("/"))')"
API_USER="$(echo "$CFG" | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_user"])')"
API_PASSWORD="$(echo "$CFG" | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_password"])')"

# ---- 命令实现 ----
status() {
  local out
  out="$(curl -s --max-time 8 -u "$API_USER:$API_PASSWORD" "$API_BASE/status")" \
    || die "无法连接 $API_BASE/status（检查网络/隧道/配置）"
  echo "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit('响应不是合法 JSON，后端可能未启动')
g = d.get('gpu', {})
print(f\"✓ 后端 OK | GPU: {g.get('name','?')} | 显存: {g.get('memory_used_mb','?')}/{g.get('memory_total_mb','?')} MB | ComfyUI: {d.get('comfyui',{}).get('status','?')} | 队列: {d.get('queue',{}).get('running',0)}跑/{d.get('queue',{}).get('pending',0)}等\")
" || exit 1
}

generate() {
  local model="" prompt="" out="" width="" height="" steps="" cfg=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --model) model="$2"; shift 2 ;;
      --prompt) prompt="$2"; shift 2 ;;
      -o) out="$2"; shift 2 ;;
      --width) width="$2"; shift 2 ;;
      --height) height="$2"; shift 2 ;;
      --steps) steps="$2"; shift 2 ;;
      --cfg) cfg="$2"; shift 2 ;;
      *) die "未知参数: $1" ;;
    esac
  done
  [ -n "$prompt" ] || die "--prompt 必填"
  [ -n "$out" ] || out="/tmp/igen_$(date +%s).png"

  local body="{\"model\": \"${model:-qwen-image}\", \"prompt\": \"$prompt\""
  [ -n "$width" ] && body="$body, \"width\": $width"
  [ -n "$height" ] && body="$body, \"height\": $height"
  [ -n "$steps" ] && body="$body, \"steps\": $steps"
  [ -n "$cfg" ] && body="$body, \"cfg\": $cfg"
  body="$body}"

  # 1. 提交任务
  local resp task_id
  resp="$(curl -s --max-time 15 -u "$API_USER:$API_PASSWORD" -X POST "$API_BASE/tasks" \
    -H "Content-Type: application/json" -d "$body")" || die "提交任务失败"
  task_id="$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("task_id",""))' 2>/dev/null)" \
    || die "提交响应解析失败: $resp"
  [ -n "$task_id" ] || die "未返回 task_id: $resp"
  echo "▶ 已提交 task_id=$task_id"

  # 2. 轮询到完成
  local st
  for i in $(seq 1 240); do  # 最多 20 分钟
    sleep 5
    st="$(curl -s --max-time 8 -u "$API_USER:$API_PASSWORD" "$API_BASE/tasks/$task_id")" || continue
    local status_val
    status_val="$(echo "$st" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)"
    if [ "$status_val" = "done" ]; then break; fi
    if [ "$status_val" = "error" ]; then
      echo "$st" | python3 -c 'import json,sys; print("✗ 任务失败:", json.load(sys.stdin).get("error","?"))' 2>/dev/null
      exit 1
    fi
  done
  [ "$status_val" = "done" ] || die "任务超时"

  # 3. 下载第一张图
  local imgs
  imgs="$(echo "$st" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("images",[])))' 2>/dev/null)"
  [ "$imgs" -ge 1 ] || die "任务完成但无图片"
  curl -s --max-time 30 -u "$API_USER:$API_PASSWORD" -o "$out" "$API_BASE/tasks/$task_id/images/0" \
    || die "下载图片失败"
  [ -s "$out" ] || die "下载文件为空"
  echo "✅ 图片已保存: $out (task_id=$task_id)"
}

download() {
  local task_id="" out="" index="0"
  while [ $# -gt 0 ]; do
    case "$1" in
      -o) out="$2"; shift 2 ;;
      --index) index="$2"; shift 2 ;;
      *) [ -z "$task_id" ] && task_id="$1" || die "多余参数: $1" ; shift ;;
    esac
  done
  [ -n "$task_id" ] || die "用法: $0 download <task_id> [-o 输出.png] [--index N]"
  [ -n "$out" ] || out="/tmp/igen_${task_id:0:8}.png"
  curl -s --max-time 30 -u "$API_USER:$API_PASSWORD" -o "$out" "$API_BASE/tasks/$task_id/images/$index" \
    || die "下载图片失败"
  [ -s "$out" ] || die "下载文件为空"
  echo "✅ 图片已保存: $out"
}

case "${1:-}" in
  status) status ;;
  generate) shift; generate "$@" ;;
  download) shift; download "$@" ;;
  *) echo "用法: $0 {status|generate|download}"; exit 1 ;;
esac
