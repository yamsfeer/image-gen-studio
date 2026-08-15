---
name: image-gen
description: 调用云端 GPU（RTX 4090 + ComfyUI）生成图片，并用视觉模型查看结果。当前支持 qwen-image（中文理解强）和 flux（英文效果强）两个模型。触发场景：用户说"生成一张图""画一只猫""帮我生图""做个图看看""生成 xxx 的图片"等。流程：验证后端 → 提交生图任务 → 轮询等待 → 下载 PNG 到本地 → 用视觉模型描述/确认结果。
---

# Image Gen（云端 GPU 生图 + 看图）

> 底层：image-gen-studio 项目的 client.py + 服务器（nginx Basic Auth → FastAPI 服务层 → ComfyUI → RTX 4090）。
> 本 skill 的脚本 `scripts/igen.sh` **自动定位项目根**（仓库内 `.pi/skills/` 或全局 `~/.agents/skills/` 都能用），无需改路径。

## 核心用法（用脚本，不要直接调 client.py）

```bash
# 脚本路径（按实际位置选择其一）
IGEN=scripts/igen.sh                          # 项目内：cd <repo> 后相对路径
IGEN=~/.agents/skills/image-gen/scripts/igen.sh   # 全局安装时

# 1. 验证后端（必须返回 ✓ 才能继续）
$IGEN status

# 2. 生图（qwen-image：中文强，自动用 12步 cfg1.0 最佳参数）
$IGEN generate --model qwen-image --prompt "一只橘猫坐在窗台上" -o /tmp/igen_result.png

# 3. 生图（flux：英文效果好，自动用 20步 cfg1.0）
$IGEN generate --model flux --prompt "A cozy cabin in snowy mountains at sunset" -o /tmp/igen_flux.png

# 4. 看图（有 deepseek-vision 就用视觉模型描述；没有则提示用 read 直接查看）
$IGEN view /tmp/igen_result.png
```

## 参数说明

- `--model`：`qwen-image`（默认，中文 prompt 首选）/ `flux`（英文 prompt 首选）
- `--prompt`：必填
- `--steps` / `--cfg`：可覆盖默认最佳参数（qwen-image 12/1.0；flux 20/1.0）
- `--width` / `--height`：默认 1024，64 的倍数
- `-o`：输出路径（默认 `/tmp/igen_<时间戳>.png`）

## 完整 Agent 操作序列

```bash
IGEN=~/.agents/skills/image-gen/scripts/igen.sh
$IGEN status                                  # ① 确认后端 OK
$IGEN generate --model qwen-image --prompt "水墨风格的山水画，云雾缭绕" -o /tmp/igen_mountain.png
$IGEN view /tmp/igen_mountain.png             # ② 看图（视觉模型返回文字描述）
# ③ 把描述结果反馈给用户
```

## 前置条件（首次使用）

1. 项目根有 `.env`（含 API_USER / API_PASSWORD / SSH 连接信息）——服务器凭据，不入库
2. SSH 隧道已建立：本机 `localhost:8080` → 服务器 8080。验证：`curl -s -u "$API_USER:$API_PASSWORD" http://localhost:8080/status`
3. 隧道断了重建：`sshpass -p "$SSH_PASSWORD" ssh -fN -o ExitOnForwardFailure=yes -p "$SSH_PORT" -L 8080:localhost:8080 "$SSH_USER@$SERVER_HOST"`
4. （可选）看图更佳：安装 deepseek-vision skill（`~/.agents/skills/deepseek-vision/`），否则 fallback 到 `read` 图片

## 常见问题

- **status 失败**：隧道断了 → 重建（见上）；或服务器 ComfyUI 挂了 → SSH 上去跑 `/root/image-service/start_all.sh`
- **图片质量差**：确认用了模型最佳参数（qwen-image 别用高步数/高 cfg）
- **404 错误**：client.py 版本旧 → `git pull` 更新仓库
- **找不到项目根**：设置 `IGEN_PROJECT_ROOT=<仓库路径>` 环境变量
