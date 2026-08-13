# 服务器 / 模型 / 工作流 现状

> 本文档给下一个接手项目的 AI 提供完整上下文。2026-08 记录，来自实际部署。

## 服务器（AutoDL 云 GPU）

| 项 | 值 |
|---|---|
| SSH | 入口见 `.env`（`SERVER_HOST`/`SSH_PORT`/`SSH_USER`，密码登录） |
| 密码 | 见 `.env` 的 `SSH_PASSWORD`（root，AutoDL 控制台可改） |
| GPU | NVIDIA RTX 2080 Ti 11GB（cuda:0） |
| 系统 | Linux 容器（AutoDL），无 systemd |
| Python | `/root/miniconda3/bin/python`（3.12，base 环境，**SSH 非交互下 PATH 没有 python，必须用绝对路径**） |
| 关键包 | torch 2.8.0+cu128、modelscope 1.39.1、fastapi 0.141、uvicorn、ComfyUI 0.31.0（git 版） |
| 数据盘 | `/root/autodl-tmp`（100G，模型都放这里，实例重启数据保留） |
| 公网 | 出网 IP 101.42.27.85；**入站只放行 SSH 映射端口**，其他端口公网直连 502 → 必须走 SSH 隧道 |

## 服务架构（当前运行中）

```
本机/Agent ──SSH隧道──▶ AutoDL nginx:8080（Basic Auth）──▶ FastAPI:8190（业务层）──▶ ComfyUI:8188（显卡）
```

| 服务 | 监听 | 位置 | 说明 |
|---|---|---|---|
| ComfyUI | 127.0.0.1:8188 | /root/autodl-tmp/ComfyUI | 生图引擎，`python main.py --listen 127.0.0.1 --port 8188` |
| 服务层 | 127.0.0.1:8190 | /root/image-service/ | FastAPI，任务管理/排队/进度/模型注册表 |
| nginx | 0.0.0.0:8080 | /etc/nginx/conf.d/comfy.conf | 反代 + Basic Auth |
| 认证 | Basic Auth | 账号/密码见 `.env`（`API_USER`/`API_PASSWORD`） | 密码存服务器 `/root/comfy_api_password.txt` |

- 一键启动脚本：`/root/image-service/start_all.sh`（ComfyUI + 服务层 + nginx reload；**实例重启后手动跑一次**）
- 后台启动方式（无 systemd，必须用）：`( cd <目录> && setsid nohup <绝对路径python> ... > log 2>&1 < /dev/null & )`

## 模型清单（全在 /root/autodl-tmp/）

| 模型 ID（API 用） | 说明 | 组件文件（ComfyUI/models 下） |
|---|---|---|
| `sd15` | SD 1.5 diffusers 格式 | models/diffusers/sd15（软链） |
| `sdxl` | SDXL base 1.0 | models/checkpoints/sd_xl_base_1.0.safetensors（6.5G 单文件） |
| `qwen-image` | Qwen-Image 20B（阿里通义千问团队），Q3_K_M GGUF 量化 | unet/Qwen_Image-Q3_K_M.gguf（9.1G）+ text_encoders/qwen2.5_vl_7b_q4_k_m.gguf（CLIP 4.4G）+ vae/qwen_image_vae.safetensors |
| `z-image-turbo` | Z-Image-Turbo 6B（阿里通义万相团队），DMD 蒸馏 8 步，fp8 | unet/z-image-turbo_fp8_scaled.safetensors（5.9G）+ text_encoders/qwen3_4b_iq4_xs.gguf（CLIP 2.2G）+ vae/z_image_vae.safetensors |
| （AnimateDiff） | 视频动画（已下载未接入 API） | models/animatediff_models/ 等 |

原始模型文件（ModelScope 下载缓存）在 `/root/autodl-tmp/models/models/<org>--<repo>/snapshots/master`，ComfyUI/models 下都是**软链**，别复制。

## 工作流（模型注册表，见 code/server/workflows.py）

每个模型两个工作流变体，通过 API 参数（steps/cfg/sampler/scheduler/宽高/seed）切换。
**默认值已按官方最佳实践更新（详见 docs/parameter-guide.md）**：

| 模型 | standard（默认，官方最佳实践） | popular（备选变体） |
|---|---|---|
| sd15 | 25步 cfg7 euler/normal 512² | 20步 cfg7 dpmpp_2m/karras 512² |
| sdxl | 20步 cfg7 euler/normal 1024² | 20步 cfg7 dpmpp_2m/karras 1024² |
| qwen-image | **12步 cfg1 res_multistep/simple 1280²**（官方蒸馏配置，实测9.5分） | 20步 cfg3.5 dpmpp_2m/karras 1280²（官方普通版推荐） |
| z-image-turbo | 8步 cfg1 dpmpp_2m/karras 1024²（实测7.7分） | 8步 cfg1 dpmpp_2m/karras 1280²（高清变体） |

> 坑：qwen-image 勿用 30 步高 cfg（实测 5.5 分）；z-image-turbo 勿用 cfg3（实测 3.0 分）。

官方参照工作流 JSON 在本项目 `workflows-official/`（Comfy-Org 仓库下载）。

## 已知坑（部署经验，重要）

- **pkill -f "main.py" 会杀自己**：用 `pkill -f "[m]ain.py"`（正则技巧）
- **后台进程**：`setsid nohup cmd > log 2>&1 < /dev/null &`，缺 stdin 重定向 SSH 会挂住
- **ComfyUI /queue 结构**：每项是 `[编号, prompt_id, ...]`，prompt_id 在 index 1
- **DiffusersLoader 是废弃节点**：加载 Z-Image（自定义 pipeline）必崩，用社区单文件（fp8/GGUF）
- **Qwen-Image 三件套**：transformer + CLIP（Qwen2.5-VL-7B）+ VAE，GGUF 仓库只有 transformer 和 VAE，CLIP 要单独下
- **Z-Image 的 CLIP 是 Qwen3-4B**（不是 Qwen2.5-VL），ComfyUI 会自动检测前缀
- **hf-mirror 限流**：大量 API 请求触发 quota，优先用 ModelScope
- **ModelScope 搜索 API 404**：探测仓库用 `curl -w "%{http_code}" https://www.modelscope.cn/api/v1/models/<org>/<repo>`
- **2080Ti 11G 跑 Qwen Q3**：模型 9G 靠 offload 撑住，约 17s/步（30 步 ≈ 8.5min）；Z-Image fp8 40s/张

## 客户端用法（本机 code/client/client.py）

```bash
python3 client.py generate --model qwen-image --prompt "..." [--steps 30 --cfg 4 --width 1024 --height 1024 --sampler euler --scheduler karras --seed 42] --wait -o out.png
python3 client.py task <task_id>
python3 client.py image <task_id> -o out.png
python3 client.py stats
python3 client.py models
```

依赖：走 `http://localhost:8080`（本机隧道），账号/密码从 `.env` 读取（`API_USER`/`API_PASSWORD`），改密码需同步改 `.env` 与服务器。
