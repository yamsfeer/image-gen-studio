# 部署 runbook：换机器 / 全新环境

> 目标：不管是「AutoDL 同实例重启」「换新 AutoDL 实例」，还是「换到另一台 Linux + GPU 服务器」，
> 都能按这里的步骤把整条链路跑通。所有连接信息、凭据、路径都在项目根 `.env`，换环境只改 `.env`。

## 一、先分清三种场景

| 场景 | 数据盘 | 要做什么 |
|---|---|---|
| A. 同一 AutoDL 实例关机重启 | 不丢（`/root/autodl-tmp` 保留） | 只跑一次 `start_all.sh` |
| B. 换新 AutoDL 实例 / 重置 | **丢** | 完整五步（见下） |
| C. 换到另一台 Linux + NVIDIA 驱动机器 | 全新 | 完整五步 + 可能要改 `.env` 路径 |

> 边界：出图是 GPU 绑定负载。目标机器必须是**已装 NVIDIA 驱动的 Linux**（Windows 用户走 WSL2 + GPU passthrough）。
> CUDA 运行库和 torch 由环境提供，任何脚本都替代不了宿主机上的显卡内核驱动。

## 二、配置（.env）

所有可变项集中在 `.env`（模板 `.env.example`），已被 `.gitignore` 忽略：

```bash
# 云端服务器 SSH 入口
SERVER_HOST=              # 例：region-41.seetacloud.com
SSH_PORT=                 # 例：53278
SSH_USER=root
SSH_PASSWORD=

# 后端 API 地址与 Basic Auth
API_BASE=http://localhost:8080
API_USER=comfy
API_PASSWORD=

# 服务器端路径（AutoDL 默认即可）
REMOTE_DIR=/root/image-service
PYTHON_BIN=/root/miniconda3/bin/python
DATA_DIR=/root/autodl-tmp
```

**换环境时的三个常见变化**：`SSH_PORT`（AutoDL 换实例必变）、`SERVER_HOST`、`SSH_PASSWORD`。

## 三、场景 A：同实例重启（最简单）

```bash
# 服务器上跑（或本机 ssh 过去跑）
/root/image-service/start_all.sh
```

它会拉起 ComfyUI(8188) + FastAPI(8190) + nginx reload，幂等可重跑。

## 四、场景 B/C：完整五步（全新环境）

```bash
# 0. 拿到新服务器信息，改 .env（SERVER_HOST / SSH_PORT / SSH_PASSWORD / ...）
cp .env.example .env && vim .env

# 1. 重建环境（ComfyUI + 插件 + 模型 + nginx，约 1-2 小时）
source .env
sshpass -p "$SSH_PASSWORD" scp -P "$SSH_PORT" scripts/setup-server.sh "$SSH_USER@$SERVER_HOST":/root/
sshpass -p "$SSH_PASSWORD" ssh -p "$SSH_PORT" "$SSH_USER@$SERVER_HOST" \
  "API_PASSWORD='$API_PASSWORD' bash /root/setup-server.sh"

# 2. 同步服务层代码 + 启动 uvicorn(8190) + 验证
./deploy.sh

# 3. 启动 ComfyUI(8188) + nginx reload（start_all.sh 幂等）
sshpass -p "$SSH_PASSWORD" ssh -p "$SSH_PORT" "$SSH_USER@$SERVER_HOST" \
  '/root/image-service/start_all.sh'

# 4. 本机建 SSH 隧道（端口用新值）
sshpass -p "$SSH_PASSWORD" ssh -fN -o ExitOnForwardFailure=yes -p "$SSH_PORT" \
  -L 8080:localhost:8080 "$SSH_USER@$SERVER_HOST"

# 5. 逐层验证（从底层往上）
cd client
python3 client.py models          # nginx + FastAPI 通不通
python3 client.py stats           # 显卡/队列有没有
python3 client.py generate --model sd15 --prompt "test" --wait -o t.png   # 端到端出图（sd15 最快）
cd .. && python3 webui/app.py     # 前端再走一遍「选预设 → 生成」
```

### 步骤说明

- **步骤 1（setup）**：装 ComfyUI 本体 + GGUF 插件 + 4 个模型（软链）+ nginx + 生成 `start_all.sh`。
  幂等，可重跑。`API_PASSWORD` 会写入服务器 `/root/comfy_api_password.txt` 并设为 nginx Basic Auth 密码。
- **步骤 2（deploy）**：`rsync` 同步 `server/` → 服务器 + `pkill uvicorn` + 重启 + `curl /status` 验证。
  只负责服务层，**不会启动 ComfyUI**。
- **步骤 3（start_all）**：拉起 ComfyUI(8188) + nginx reload（uvicorn 若已由 deploy 启动则跳过）。
- **步骤 4（隧道）**：AutoDL 入站只放行 SSH 端口，nginx:8080 必须经 SSH 隧道从本机 `localhost:8080` 访问。
- **步骤 5（验证）**：按依赖链从下往上验证，问题定位更快。

## 五、服务端三层（部署对象）

```
前端 → nginx:8080（唯一对外入口，Basic Auth）→ FastAPI:8190（API 服务层）
                                                        │ 内部直连 127.0.0.1
                                                        ▼
                                             ComfyUI:8188（持模型、占显卡）
```

- nginx 只反代 8190；ComfyUI(8188) 不对外，由服务层内部直连。
- 服务层无状态，重启 2 秒；ComfyUI 常驻，模型缓存不丢。

## 六、常见坑

1. **nginx 密码不一致**：setup 若没传 `API_PASSWORD` 会随机生成，需回填到本地 `.env`，否则前端/客户端连不上。
2. **pkill 要加方括号**：`pkill -f "[u]vicorn"` / `pkill -f "[m]ain.py"`，避免杀掉自己所在 SSH 会话。
3. **别在服务器上直接改代码**：`/root/image-service/` 会被 `deploy.sh` 的 `--delete` 覆盖，本地才是唯一真源。
4. **AutoDL 换实例 SSH 端口会变**：先确认新端口再改 `.env`。
5. **Windows 目标机**：无 NVIDIA 驱动的原生 Windows 跑不动生图；用 WSL2 + Docker（见下）才是可行路径。

## 七、演进路线（本仓库已完成/规划）

| 层次 | 状态 | 说明 |
|---|---|---|
| 第 1 层：配置外置（.env） | ✅ 已完成 | 去硬编码，换环境只改 `.env` |
| 第 2 层：Docker Compose 打包 | ⏳ 规划 | ComfyUI + 服务层 + nginx 容器化，`docker compose up -d` 一条命令，真正「下载即跑」 |
| 第 3 层：前端独立安装 | ✅ 已完成 | `webui/` 只依赖 Python，可连任意后端（见 `webui/README.md`） |

第 2 层的目标形态：

```bash
# 未来：任何 Linux + NVIDIA 驱动 + nvidia-container-toolkit 的机器
docker compose up -d       # 起 ComfyUI + 服务层 + nginx
# 模型挂载数据卷 / 首次幂等下载，不烤进镜像
```
