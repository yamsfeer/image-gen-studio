# AGENTS.md —— Image Gen Studio 项目指南

> 本文件供 AI agent（pi、Claude Code 等）在项目内工作时参考。请先读完再动手。

## 项目是什么

用 AutoDL 云 GPU（RTX 2080 Ti 11GB）跑 AI 图片生成的完整项目：

- **前端**：`webui/`（Gradio Web UI，按 PLAN.md 实现，本机运行）
- **后端服务副本**：`code/server/`（FastAPI 服务层源码，**部署在云端服务器**）
- **客户端**：`code/client/`（API 调用库 + 实验脚本）
- **文档**：`docs/`（现状/API/参数经验/开发流程）
- **评测**：`benchmark/`（交叉对比结果）

## 核心架构（重要）

```
本地（本项目）                    云端 AutoDL 服务器（显卡在这）
┌──────────────────────┐   ┌─────────────────────────────┐
│ webui/ 前端 (Gradio) │   │ nginx:8080 (Basic Auth)     │
│ code/server/ 后端源码│→→→│ FastAPI:8190 (服务层，无状态)│
│ deploy.sh 部署脚本   │   │ ComfyUI:8188 (显卡+模型常驻) │
└──────────────────────┘   └─────────────────────────────┘
  隧道：本机 localhost:8080 → 服务器 8080
```

- **代码在本地（唯一真源），执行在云端**。服务器 `/root/image-service/` 是部署产物。
- 服务层无状态，重启 2 秒，不影响 ComfyUI 的模型缓存 → 后端迭代成本极低。

## 常用命令

```bash
# 部署后端：同步本地 code/server/ → 服务器 + 重启服务层 + 验证（改后端必用）
./deploy.sh

# 全新实例重建环境（ComfyUI+插件+模型+nginx，幂等）：setup/setup-server.sh scp 到服务器执行
#   详见 docs/setup.md

# 建 SSH 隧道（本机 8080 → 服务器 nginx 8080，访问服务/前端联调前先建）
# 连接信息从 .env 读（SERVER_HOST/SSH_PORT/SSH_USER/SSH_PASSWORD）
source .env
sshpass -p "$SSH_PASSWORD" ssh -fN -o ExitOnForwardFailure=yes -p "$SSH_PORT" \
  -L 8080:localhost:8080 "$SSH_USER@$SERVER_HOST"

# 生图客户端（本机）
cd code/client && python3 client.py generate --model qwen-image --prompt "一只猫" --wait -o cat.png
python3 client.py stats / models / task <id> / image <id> -o out.png

# 启动前端（本机）
python3 webui/app.py    # http://127.0.0.1:7860
```

## 服务器情报（AutoDL）

| 项 | 值 |
|---|---|
| SSH | 入口见 `.env`（`SERVER_HOST`/`SSH_PORT`/`SSH_USER`/`SSH_PASSWORD`） |
| Python | `/root/miniconda3/bin/python`（SSH 非交互 PATH 无 python，必须绝对路径） |
| 服务层 | `/root/image-service/`（uvicorn :8190），一键启动 `/root/image-service/start_all.sh` |
| ComfyUI | `/root/autodl-tmp/ComfyUI`（:8188），模型在 `models/`（软链） |
| nginx | `:8080` + Basic Auth（账号/密码见 `.env` 的 `API_USER`/`API_PASSWORD`，密码也存 `/root/comfy_api_password.txt`） |
| 无 systemd | 后台启动必须 `( cd <dir> && setsid nohup <python> ... > log 2>&1 < /dev/null & )` |

## 模型（API 的 model 字段）

| ID | 说明 | 最佳参数（勿乱改，见 docs/parameter-guide.md） |
|---|---|---|
| `qwen-image` | Qwen-Image GGUF Q3 | 12步 cfg1 res_multistep/simple 1280²（官方蒸馏配置，实测 9.5 分） |
| `z-image-turbo` | Z-Image-Turbo fp8 | 8步 cfg1 dpmpp_2m/karras（cfg3 实测翻车） |
| `sdxl` | SDXL 1.0 | 20步 cfg7 euler/normal |
| `sd15` | SD 1.5 | 25步 cfg7 euler/normal |

## 硬性约定（违反会踩坑）

- **pkill 匹配要加方括号**：`pkill -f "[m]ain.py"`、`pkill -f "[u]vicorn"`（否则杀掉自己所在 SSH 会话）
- **不要在服务器上直接改代码**：会被 deploy.sh 的 `--delete` 覆盖；要改先改本地 code/server/ 再部署
- **ComfyUI /queue 的 prompt_id 在 index 1**（每项是 `[编号, prompt_id, ...]`）
- **webui/ 由前端 agent 维护**，改它不需要部署；改 code/server/ 才需要 ./deploy.sh

## 文档索引（改代码前先读对应文档）

- `docs/server-status.md` —— 服务器/模型/服务现状 + 全部踩坑
- `docs/api.md` —— 后端 API 参考（/generate /task /image /stats /models）
- `docs/parameter-guide.md` —— 参数调优认知 + 最佳实践（为什么用这些参数）
- `docs/dev-workflow.md` —— 本地改代码 → 云端部署 → 前端看效果
- `docs/deployment.md` —— 换机器/全新环境部署 runbook（setup → deploy → start_all → 隧道 → 验证）
- `PLAN.md` —— 前端 Web UI 计划（webui/ 的实现依据）
- `benchmark/README.md` —— 交叉对比评测结果
