# 开发工作流：本地改后端 → 云端显卡 → 前端看效果

> 代码在本地（git 管理），执行在云端（显卡在 AutoDL 服务器）。本文说明如何快速迭代。

## 架构回顾

```
本地（本项目）                    云端 AutoDL 服务器
┌─────────────────────┐   ┌──────────────────────────────┐
│ webui/ 前端 (Gradio) │   │ nginx:8080 (Basic Auth)      │
│ code/server/ 后端源码│→→→│ FastAPI:8190 (服务层，无状态) │
│ deploy.sh 部署脚本   │   │ ComfyUI:8188 (显卡，模型常驻) │
└─────────────────────┘   └──────────────────────────────┘
       隧道：本机 localhost:8080 → 服务器 8080
```

**关键事实**：服务层是无状态进程，重启仅 2 秒；ComfyUI 的模型加载/显卡缓存不受影响。
所以后端迭代成本极低——同步代码 → 重启 → 前端刷新即见效果。

## 日常开发循环（推荐）

```bash
# 1. 本地改代码（code/server/service.py 或 workflows.py）

# 2. 一条命令部署（同步 + 重启 + 验证）
./deploy.sh

# 3. 前端看效果
#    - webui 已开着 → 直接刷新页面
#    - 或浏览器开 http://localhost:8080（需隧道已建）
```

## 可选：热重载（更顺滑）

服务器上让 uvicorn 带 `--reload` 跑，改完代码同步后**自动重启**，无需手动 pkill：

```bash
# 服务器上启动（带热重载；路径变量见 .env，AutoDL 默认值如下）
( cd "${REMOTE_DIR:-/root/image-service}" && \
  setsid nohup "${PYTHON_BIN:-/root/miniconda3/bin/python}" \
  -m uvicorn service:app --host 127.0.0.1 --port 8190 \
  --reload --reload-dir "${REMOTE_DIR:-/root/image-service}" \
  > server.log 2>&1 < /dev/null & )
```

> 注意：`--reload` 会额外占一个监视进程；deploy.sh 的 pkill 模式要改成只杀 uvicorn 主进程。
> 生产环境建议关掉 --reload（用 deploy.sh 的重启方式）。

## 可选：本地文件变化自动同步（Mac）

用 `fswatch` 监听本地 code/server/，变化自动 rsync + 重启：

```bash
# 需要先装 fswatch（brew install fswatch）
fswatch -o code/server | while read; do ./deploy.sh; done
```

## 注意

- **别在服务器上直接改代码**（/root/image-service/ 会被 deploy.sh 的 `--delete` 覆盖）。
  服务器目录 = 部署产物，本地 = 唯一真源。
- 改 workflows.py（模型/工作流）后同样跑 deploy.sh 即可生效。
- 改 webui/（前端）不需要部署——webui 就在本机跑。
