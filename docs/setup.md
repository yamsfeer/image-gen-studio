# 部署可复现性说明

> 目标：全新 AutoDL 实例也能一键恢复全部环境，不丢任何部署资产。
> 脚本：`setup/setup-server.sh`（幂等，可重跑）。本文说明资产清单与使用流程。

## 为什么需要

ComfyUI 不是"NPM 包式自动依赖"——它由 **本体 + 插件 + 模型文件 + nginx 配置 + 启动脚本** 五类资产组成，
都是手动部署的。没有脚本化就会"换机器就丢配置、漏装插件、忘软链模型"。

## 资产清单（本脚本覆盖了什么）

| 资产 | 来源 | 放哪 |
|---|---|---|
| ComfyUI 本体（git） | `gitclone.com/github.com/comfyanonymous/ComfyUI` | /root/autodl-tmp/ComfyUI |
| ComfyUI-GGUF 插件 | gitclone（city96） | custom_nodes/ |
| AnimateDiff 插件（可选） | gitclone（Kosinkadink） | custom_nodes/ |
| Qwen-Image GGUF Q3 + VAE | ModelScope QuantStack/Qwen-Image-GGUF | models/unet, models/vae |
| Qwen CLIP（Qwen2.5-VL-7B Q4） | ModelScope unsloth/Qwen2.5-VL-7B-Instruct-GGUF | models/text_encoders |
| Z-Image-Turbo 全套（30G） | ModelScope Tongyi-MAI/Z-Image-Turbo | models/diffusers |
| Z-Image unet fp8 | hf-mirror Kijai/Z-Image_comfy_fp8_scaled | models/unet |
| Z-Image CLIP（Qwen3-4B Q4） | hf-mirror worstplayer/Z-Image_Qwen_3_4b_text_encoder_GGUF | models/text_encoders |
| SD 1.5 diffusers | ModelScope AI-ModelScope/stable-diffusion-v1-5 | models/diffusers |
| SDXL diffusers + 单文件 | ModelScope AI-ModelScope/stable-diffusion-xl-base-1.0 | models/diffusers, checkpoints |
| 模型软链 | 脚本自动建立（缓存 → ComfyUI/models/） | — |
| pip 依赖 | fastapi uvicorn gguf modelscope requests | miniconda base |
| nginx 反代 + Basic Auth | 脚本自动写 /etc/nginx/conf.d/comfy.conf | nginx:8080 |
| 启动脚本 | /root/image-service/start_all.sh（ComfyUI+服务层+nginx） | 服务器 |

## 全新实例恢复流程

```bash
# 1. 配置：复制 .env.example 为 .env 并填写真实值（连接信息 + 凭据）
cp .env.example .env

# 2. 把重建脚本传到服务器（本机执行）
source .env
sshpass -p "$SSH_PASSWORD" scp -P "$SSH_PORT" setup/setup-server.sh "$SSH_USER@$SERVER_HOST":/root/

# 3. 服务器上执行（首次装模型约 1-2 小时，重跑只补缺失）
#    用 API_PASSWORD 指定 nginx 密码，保证与本地 .env 一致
sshpass -p "$SSH_PASSWORD" ssh -p "$SSH_PORT" "$SSH_USER@$SERVER_HOST" \
  "API_PASSWORD='$API_PASSWORD' bash /root/setup-server.sh"

# 4. 本机同步服务层代码并启动（deploy.sh 已含同步+重启+验证）
./deploy.sh
```

## 注意事项

- **模型下载走 ModelScope 为主**，只有 Kijai fp8 和 Qwen3-4B CLIP 两个文件走 hf-mirror（ModelScope 没有）。
- 脚本**幂等**：已存在的文件/目录自动跳过，重跑安全。
- SDXL 单文件 ckpt（checkpoints/）依赖历史缓存的 sdxl_single 目录；若新实例没有，脚本会提示手动处理（可用 `dl_sdxl_single.py` 的方式重新下载，见 docs/server-status.md）。
- AutoDL 数据盘 `/root/autodl-tmp` **关机不丢**（保存镜像也不丢，但换实例/重置会丢）——换实例必须重跑本脚本。
- 服务层代码（code/server/）**始终以本地为准**，deploy.sh 负责同步；setup 脚本不包含服务层源码（避免双份真源）。
- **nginx 密码一致性**：脚本用 `API_PASSWORD` 环境变量设置 Basic Auth 密码并写入 `/root/comfy_api_password.txt`。若未提供，会随机生成并提示你回填到本地 `.env`——务必回填，否则本地前端/客户端连不上。
- 所有路径变量（`PYTHON_BIN` / `DATA_DIR` / `COMFY_DIR` / `REMOTE_DIR`）均有 AutoDL 默认值，可用环境变量覆盖，便于换到其它 Linux 服务器。
