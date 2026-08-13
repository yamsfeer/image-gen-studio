# Image Gen Studio —— ComfyUI 生图服务 + Web UI

> 用 AutoDL 云服务器（RTX 2080 Ti 11GB）跑 AI 图片生成的完整项目：
> 后端 = 包装 ComfyUI 的 HTTP API 服务；前端 = 待开发的 Web UI（预设工作流 + 提示词一键生图）。

## 项目结构

```
image-gen-studio/
├── README.md                  # 本文件：项目总览
├── PLAN.md                    # 前端 Web UI 开发计划（交给执行 agent）
├── docs/
│   ├── server-status.md       # 服务器/模型/工作流现状（给下一个 AI 的上下文）
│   ├── api.md                 # 后端 API 参考
│   ├── parameter-guide.md     # 参数调优认知 + 最佳实践（重要经验）
│   ├── dev-workflow.md        # 本地改代码→云端部署→前端看效果 的开发流程
│   └── setup.md               # 部署可复现性：资产清单 + 全新实例重建流程
├── deploy.sh                  # ★ 一键部署：同步后端代码到服务器 + 重启服务层
├── setup/
│   └── setup-server.sh        # ★ 服务器一键重建（幂等）：ComfyUI+插件+模型+nginx
├── code/
│   ├── client/                # 客户端脚本（可直接用）
│   │   ├── client.py          #   生图服务客户端库（generate/task/image/stats）
│   │   └── benchmark.py       #   交叉对比实验脚本（4模型×2工作流=8张图）
│   ├── server/                # 服务端（部署在 AutoDL 服务器 /root/image-service/）
│   │   ├── service.py         #   FastAPI 服务层
│   │   └── workflows.py       #   模型注册表 + ComfyUI 工作流构造器
│   └── tools/
│       └── make_html.py       # 把实验结果 + 视觉评分生成 HTML 对比页
├── workflows-official/        # 官方工作流（Comfy-Org 仓库下载，作参照）
├── benchmark/                 # ★ 交叉对比评测结果
│   ├── README.md              #   评测说明（模型/参数/评分/发现）
│   ├── benchmark.html         #   可视化对比页（浏览器打开）
│   ├── results.json           #   原始数据
│   └── images/                #   8 张生成图（4模型×2工作流）
├── webui/                     # ★ Web UI（按 PLAN.md 实现，见其内部 README）
└── artifacts/
    └── images/                # 各模型单张测试图
```

## 快速开始（本机调用生图服务）

```bash
# 0. 首次：复制配置模板并填写真实值
cp .env.example .env            # 填 SERVER_HOST / SSH_PORT / SSH_PASSWORD 等

# 1. 建 SSH 隧道（本机 8080 → 服务器 nginx 8080）
source .env
sshpass -p "$SSH_PASSWORD" ssh -fN -o ExitOnForwardFailure=yes -p "$SSH_PORT" \
  -L 8080:localhost:8080 "$SSH_USER@$SERVER_HOST"

# 2. 用客户端生图（client 自动读 .env 的 API_*）
cd code/client
python3 client.py generate --model qwen-image --prompt "一只猫" --wait -o cat.png
python3 client.py stats          # 看显卡状态
python3 client.py models         # 看可用模型
```

详细现状（服务器地址、模型清单、踩坑记录）见 [docs/server-status.md](docs/server-status.md)。

## 配置（.env）

所有连接信息、凭据、路径统一从项目根 `.env` 读取（模板见 `.env.example`）：

| 变量 | 说明 |
|---|---|
| `SERVER_HOST` / `SSH_PORT` / `SSH_USER` / `SSH_PASSWORD` | 云端服务器 SSH 入口 |
| `API_BASE` / `API_USER` / `API_PASSWORD` | 后端 API 地址与 Basic Auth |
| `REMOTE_DIR` / `PYTHON_BIN` / `DATA_DIR` | 服务器端路径（AutoDL 默认即可） |

`.env` 已被 `.gitignore` 忽略，不会提交；换机器只需改 `.env`，不动脚本逻辑。

## 当前能力

- 4 个模型可切换：SD 1.5 / SDXL 1.0 / Qwen-Image / Z-Image-Turbo
- 每个模型支持参数覆盖（步数/cfg/采样器/调度器/分辨率/seed）
- 任务排队 + 实时进度 + 图片下载
- 交叉对比实验已验证（见 PLAN.md 和 code/benchmark.py）

## 下一步（见 PLAN.md）

开发一个 Web UI：预设选择（模型 × 工作流）→ 填提示词 → 点运行 → 调后端 API 生图 → 展示结果。
