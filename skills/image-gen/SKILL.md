---
name: image-gen
description: 调用云端 GPU 生图服务（本项目后端 API）生成图片并下载到本地。本 Skill 只负责一件事：提交生图任务 → 轮询 → 下载 PNG。不包含看图、调参建议等其它能力。使用前需要配置（API 地址 + 凭据），首次使用时 Agent 必须向用户提问获取配置并写入本 Skill 目录下的 config.json。触发场景：用户说"生成一张图""帮我画一只猫""用 GPU 生个图"等。
---

# Image Gen（云端 GPU 生图）

调用本项目部署的云端生图后端（nginx → FastAPI 服务层 → ComfyUI → GPU），提交任务并下载图片。

## ⚠️ 配置要求（首次使用必读）

本 Skill 需要连接配置才能工作。**Agent 首次使用时，必须向用户提问获取以下信息**，不能假设、不能猜、不能从别处读：

1. **API 地址**（如 `http://localhost:8080`，通常是 SSH 隧道后的本机端口）
2. **用户名**（Basic Auth）
3. **密码**（Basic Auth）
4. （可选）**默认模型**，如 `qwen-image` / `flux`

将用户提供的值写入本 Skill 目录下的 `config.json`（与本文件同级）：

```json
{
  "api_base": "http://localhost:8080",
  "api_user": "comfy",
  "api_password": "用户提供的密码",
  "model": "qwen-image"
}
```

- 配置只保存在 `config.json`，**不要**把密码写进对话、提示词或代码
- 之后每次调用前，先检查 `config.json` 是否存在且字段完整；缺失则回到提问流程
- 模板见同目录 `config.example.json`

## 用法（脚本读 config.json，无需其它参数）

```bash
# 脚本位置（与 SKILL.md 同目录）
IGEN="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/scripts/igen.sh"
# 或按实际安装位置直接写：~/.agents/skills/image-gen/scripts/igen.sh

# 1. 检查后端是否可达
bash "$IGEN" status

# 2. 生图（阻塞到完成，输出 PNG 路径 + task_id）
bash "$IGEN" generate --model qwen-image --prompt "一只橘猫坐在窗台上"

# 3. 指定输出路径 / 覆盖模型
bash "$IGEN" generate --model flux --prompt "A cozy cabin" -o /tmp/flux.png

# 4. 单独下载已提交的任务（知道 task_id 时）
bash "$IGEN" download <task_id> -o /tmp/out.png
```

## 命令与输出约定

- `status`：GET `/status`，返回后端/GPU/队列状态；失败时提示检查 config.json 与网络
- `generate`：POST `/tasks` 提交 → 轮询 `GET /tasks/{id}` 到 done → 下载第一张图到 `-o` 指定路径（默认 `/tmp/igen_<时间戳>.png`），输出 `task_id` 和文件路径
- `download`：GET `/tasks/{id}/images/{index}` 下载第 N 张图（默认 0）

## 边界（本 Skill 不做的事）

- ❌ 不看图 / 不描述图片（那是视觉类 Skill 的事）
- ❌ 不推荐提示词 / 参数（调用方决定）
- ❌ 不管服务器运维 / SSH 隧道（连接不通时提示用户，不自行处理）

## 常见问题

- **status 失败**：配置可能错误，或隧道未建立、后端未启动 → 提示用户检查
- **generate 报 401**：config.json 凭据错误 → 重新向用户提问更新配置
- **找不到 config.json**：回到「配置要求」流程向用户提问
