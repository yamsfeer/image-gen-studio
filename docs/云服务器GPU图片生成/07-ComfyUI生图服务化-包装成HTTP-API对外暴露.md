# ComfyUI 生图服务化：包装成 HTTP API 对外暴露

> 第二阶段：把 ComfyUI 后端包装成"别的 Agent 能调用的生图服务"。含架构、接口设计、模型下载续传、全部踩坑。2026-08

## 背景与目标

第一阶段已跑通 ComfyUI（RTX 2080 Ti 11G）。第二阶段目标：**别的 Agent 通过 HTTP API 调用生图**——请求指定模型+提示词 → 服务器驱动显卡生成 → 任务多自动排队 → 轮询进度 → 下载成图。对外要有账号密码保护。

## 最终架构（全链路）

```
Agent/浏览器 ──▶ 本机 localhost:8080（SSH 隧道）
                    │
                    ▼
             AutoDL: nginx:8080（Basic Auth: comfy/密码）
                    │  proxy_pass
                    ▼
             FastAPI 服务层:8190（任务管理/排队/GPU状态/模型注册表）
                    │  requests + WebSocket 进度监听
                    ▼
             ComfyUI:8188（显卡驱动，RTX 2080 Ti）
```

- **SSH 隧道**：AutoDL 公网 NAT 只放行映射端口（直连 101.42.27.85:8080 返回 502），所以用 `ssh -fN -L 8080:localhost:8080` 从本机打通，所有调用走本机端口。
- **nginx 管认证**：Basic Auth 一层挡在入口，ComfyUI 8188 只监听 127.0.0.1，外部无法绕过。
- **FastAPI 管业务**：模型注册表、任务状态机（submitted→queued→running→done/error）、排队位置、实时进度、图片下载。

## 服务层接口（Agent 集成模板）

| 接口 | 作用 | 关键返回 |
| POST /generate | 提交任务（model/prompt/宽高/steps/cfg/seed） | task_id（立即返回） |
| GET /task/{id} | 轮询状态 | status、queue_position、progress、images URL |
| GET /image/{id} | 下载图片（?index= 多图） | PNG 二进制 |
| GET /stats | GPU 状态 + 队列长度 | 显存/利用率/温度/running/pending |
| GET /models | 模型列表 | 各模型默认参数 |

模型注册表（workflows.py）三个模型：

- **qwen-image**：Qwen-Image Q3_K_M（GGUF 量化）+ Qwen2.5-VL-7B CLIP + Qwen VAE，中文理解强，默认 30 步 cfg4
- **sdxl**：SDXL base 1.0 单文件，默认 20 步 cfg7（已验证 16s 出图）
- **z-image-turbo**：diffusers 格式，Turbo 少步数（8 步），待验证

## 模型下载经验（ModelScope 为主）

**断点续传是默认行为。** `snapshot_download` 遇到 `.incomplete` 残留文件会自动从断点继续，不用删了重下。本次 Qwen GGUF 从 31% 断点续传到完成、Z-Image 分片断点续传均成功。

**三个模型组件的来源（Qwen-Image 需三件套）：**

| 组件 | 仓库 | 大小 |
| transformer | QuantStack/Qwen-Image-GGUF（ModelScope） | 9.1G |
| VAE | 同仓库 VAE/ 子目录 | 242M |
| CLIP 文本编码器 | unsloth/Qwen2.5-VL-7B-Instruct-GGUF（ModelScope） | 4.4G |

**注意坑：** GGUF 仓库只有 transformer + VAE，**不含 CLIP**；CLIP 用 Qwen2.5-VL-7B 量化版（Q4_K_M 4.4G，比 fp8 的 9G 省一半显存）。

## 踩坑清单（按惨痛程度排序）

- **`pkill -f "main.py"` 会杀掉自己。** 命令行的 bash -c 进程也匹配 "main.py" 字符串，pkill 连同 SSH 会话一起杀，表现为"命令没输出、服务没启动"。用正则技巧 `pkill -f "[m]ain.py"` 规避。
- **SSH 非交互无 PATH。** `python` 找不到，必须用绝对路径 `/root/miniconda3/bin/python`；`ss`、`python3` 也可能没有。
- **后台进程要三件套。** `setsid nohup python ... > log 2>&1 < /dev/null &`——缺 `setsid` 或 stdin 重定向时，SSH 会话会挂住不退出（表现为命令被 abort）。
- **AutoDL 无 systemd。** 服务靠 `setsid nohup` 常驻 + 一键脚本 `/root/image-service/start_all.sh`（实例重启后手动跑一次）。
- **hf-mirror 会限流。** 短时间大量 API 请求触发 "quota of 100000 resolvers requests"，下载得到 317 字节错误页。**优先用 ModelScope**，只有 ModelScope 没有的才考虑 hf-mirror。
- **ModelScope 搜索 API 是 404。** 网页搜索是 SPA（curl 拿不到），`list_models` 只支持按 owner。**探测仓库存在性用 HTTP 状态码**：`curl -w "%{http_code}" https://www.modelscope.cn/api/v1/models/组织/仓库`，200=存在。
- **ComfyUI /queue 结构是陷阱。** 每项是 `[编号, prompt_id, workflow...]`，**prompt_id 在 index 1** 不是 0。取错导致排队位置永远显示 None。
- **Qwen-Image 的 mmproj 警告可忽略。** "Can't find mmproj file" 和 `clip missing: visual.*` 只影响 Qwen-Image-**Edit**（图像编辑），纯文生图不受影响。
- **2080Ti 11G 跑 Qwen Q3_K_M 很勉强。** 模型加载 8993MB 靠 offload 撑住，约 17s/步，30 步 ≈ 8.5 分钟，显存 97%、温度 63°C。想要更快需换更小量化或 Z-Image-Turbo（Turbo 少步数）。
- **DiffusersLoader 是废弃节点，加载 Z-Image 必崩。** Z-Image 用自定义 `ZImagePipeline`，`comfy.diffusers_load` 处理时 `'NoneType' has no attribute 'lower'`。且它只认 `models/diffusers` 下的相对路径。**正确姿势：用社区转换的单文件**——unet 用 Kijai 的 `Z-Image_comfy_fp8_scaled`（5.9G，UNETLoader 加载），text encoder 用 `Qwen3-4B GGUF`（Z-Image 的文本编码器是 Qwen3-4B，不是 Qwen2.5-VL！），VAE 用 diffusers 目录里的单文件。CLIP 加载时会**自动检测** qwen3_4b 前缀并匹配 Z-Image 配置（comfy/sd.py 里 te_model 检测），type 参数随便传。
- **Z-Image 是 6B 单流 DiT + Qwen3-4B 文本编码器。** 与 Qwen-Image（20B MMDiT + Qwen2.5-VL-7B）不同，注意 CLIP 不要混用。
- **磁盘规划。** 数据盘 100G：Qwen 9.1G + Z-Image 30G + SD 系列 + CLIP/VAE，全下完约 48G 占用。模型文件用**软链**进 ComfyUI/models/，避免复制双倍空间。

## 常用命令速查

```bash
# 一键启动（ComfyUI + 服务层 + nginx reload）
/root/image-service/start_all.sh

# 本机建 SSH 隧道（连接信息从项目根 .env 读取）
sshpass -p "$SSH_PASSWORD" ssh -fN -o ExitOnForwardFailure=yes -p "$SSH_PORT" \
  -L 8080:localhost:8080 "$SSH_USER@$SERVER_HOST"

# 客户端调用（本机 /tmp/image-service/client.py）
python3 client.py generate --model qwen-image --prompt "一只猫" --wait -o cat.png
python3 client.py task <task_id>
python3 client.py stats

# 改密码
htpasswd -b /etc/nginx/.htpasswd comfy 新密码
```

## 进度备忘

- 已完成：SD1.5、SDXL（双版本）、AnimateDiff、Qwen-Image GGUF 全套、Z-Image-Turbo（30G）
- 已验证：SDXL API 全链路 16s 出图 ✅；Qwen-Image 正常出图（8.5min/张）✅；排队机制 ✅
- 待验证：z-image-turbo 工作流（diffusers 加载）、HTTPS 化、隧道自动保活（autossh）
