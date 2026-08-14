# 在云服务器 GPU 上部署 AI 图片生成全记录

> 从零到跑通：diffusers 直调 → ComfyUI 工作流 + LCM 加速，含全部踩坑与性能数据。2026-08

## 背景与目标

租了一台 AutoDL 云服务器（RTX 2080 Ti 11GB），目标是用它的显卡**跑通"AI 生成一张普通图片"的完整链路**：CUDA → Python → PyTorch → 模型加载 → 推理出图。效果只要能用就行，重点是**跑通 + 跑得快 + 能批量**，充分利用 GPU 算力。

## 两条技术路线（本仓库的核心内容）

生成图片本质都是 Stable Diffusion 扩散模型，但调用方式分两种，我们两条都跑通了：

| 维度 | 路线一：diffusers 直调 | 路线二：ComfyUI（最终采用） |
|------|----------------------|---------------------------|
| 本质 | Python 代码直接调库 | 节点式工作流引擎（可视化/API） |
| 灵活性 | 代码控制，改 prompt 要改代码 | 拖节点连线，改参数可视化 |
| 加速生态 | 需自己写优化代码 | 原生支持 LCM / TensorRT 等 |
| 批量生产 | 要自己写循环 | 常驻服务 + 队列，天然适合批量 |
| 效果 | 相同模型相同效果 | 相同（但调优手段更多） |

**结论：ComfyUI 胜出**——它默认就是"加载一次模型、连续吃任务"的常驻服务，加速节点齐全，正是"GPU 满负荷批量出图"的正确工具。

## 环境清单（踩坑后的最终版本）

| 组件 | 版本 | 来源 |
|------|------|------|
| 驱动 | 580.105.08（CUDA 13.0 驱动级） | AutoDL 预装 |
| Python | 3.12.3（miniconda base） | AutoDL 预装 |
| PyTorch | 2.8.0+cu128（GPU 可用） | AutoDL 预装 |
| diffusers | 0.39.0 | pip（阿里云源） |
| ModelScope | 1.39.1 | pip（阿里云源） |
| ComfyUI | 0.31.0 | git clone（学术加速） |
| 基础模型 | stable-diffusion-v1-5（fp32，4GB） | ModelScope 下载 |
| 加速模型 | LCM-LoRA for SD1.5（129MB） | HuggingFace 下载 |

## 部署过程拆解

### 第一步：网络侦察（决定一切的前提）

先测两端到 GitHub 的下载速度，结果**惊出一身冷汗**：

```
服务器直连 GitHub：33 KB/s（10 秒下 337KB）
本机直连 GitHub：  31 KB/s（10 秒下 312KB）
```

**4GB 的模型按这速度要下 30 小时+。** 结论：这台机器的出口网络访问 GitHub 就是慢，本地"下载再传"没意义。

三把钥匙破解：

- **服务器侧**：AutoDL 自带学术加速 `/etc/network_turbo`（GitHub/HF 走内网代理）
- **本地侧**：翻墙代理端口 7897 可用（`HTTPS_PROXY=http://127.0.0.1:7897`）
- **国内源**：pip 走阿里云、模型走 ModelScope（国内 CDN）

实测：本地走代理下 ComfyUI 依赖的 GitHub Release **58MB 几秒下完**；ModelScope 下模型 **4GB / 6 分钟**（约 11MB/s）。

### 第二步：diffusers 直调路线（快速验证）

```
pip install diffusers modelscope transformers accelerate safetensors
→ modelscope 下载 AI-ModelScope/stable-diffusion-v1-5（只取推理文件，4GB）
→ StableDiffusionPipeline.from_pretrained(fp16) → 出图
```

生成 25 步 512×512 仅 **2 秒**（11.8 步/秒）。**链路首次跑通**：CUDA → 模型 → 出图全 OK。产物见 `images/01-diffusers直调-普通25步.png`。

### 第三步：ComfyUI 路线（正式方案）

```
git clone ComfyUI（学术加速，几秒）→ pip 装依赖（关加速，阿里云源）
→ 模型软链接进 models/diffusers/（零拷贝）
→ 下载 LCM-LoRA → 启动服务（--listen 127.0.0.1:8188）
```

**ComfyUI 工作流结构**（节点图，LCM 加速版）：

```
DiffusersLoader(sd15) ──┬── model ──→ LoraLoader(LCM) ──→ model ─┐
                        ├── clip ───→ LoraLoader(LCM) ──→ clip ──┤
                        └── vae ──────────────────────────────┐  │
CLIPTextEncode(正向词) ──────────────→ positive ──┐            │  │
CLIPTextEncode(负向词) ──────────────→ negative ──┼→ KSampler ─┤  │
EmptyLatentImage(512×512) ──────────→ latent ────┘  (steps=4,  │  │
                                                     cfg=1.0,   │  │
                                                     sampler=lcm)│  │
                                                     samples ──→ VAEDecode ──→ SaveImage
```

关键参数（LCM 与普通模式的区别）：

| 参数 | LCM 加速 | 普通模式 |
|------|---------|---------|
| 采样步数 | **4** | 25 |
| CFG | **1.0**（蒸馏模型不需要引导） | 7.5 |
| 采样器 | **lcm** | dpmpp_2m |
| 调度器 | normal | karras |
| 加速器 | LCM-LoRA 挂载 | 无 |

## 性能对比（同一 GPU 实测）

| 方案 | 单张耗时 | 批量吞吐（串行 8 张） | 相对提速 |
|------|---------|---------------------|---------|
| diffusers 直调 25 步 | ~2.0s | - | 基准 |
| ComfyUI 普通 25 步 | ~2.5s | 0.40 张/秒 | 1× |
| **ComfyUI + LCM 4 步** | ~0.75s | **1.33 张/秒** | **3.3×** |
| **LCM + batch=4** | ~0.5s/张 | **~2.0 张/秒** | **5×** |

**提速原理（第一性原理）**：生成耗时 ≈ 采样步数 × 每步耗时。普通 SD1.5 要 25-30 步才收敛；**LCM（Latent Consistency Model）是蒸馏模型**，通过一致性蒸馏让 1-4 步就能逼近同样结果——步数直接除以 6，速度就上来了。配合 batch 并行（GPU 同时算多张），吞吐再翻倍。

**质量没损失**：视觉模型对 LCM 4 步和普通 25 步的图给出同级评价（"画质高、无严重变形"）。对比图：

![[02-comfyui-LCM4步.png]]
*ComfyUI + LCM 4 步（0.75s/张）—— 最终采用的方案*

![[03-comfyui-普通25步.png]]
*ComfyUI 普通 25 步（2.5s/张）*

## 踩坑记录（按时间顺序，含解法）

### 坑 1：GitHub 下载龟速（网络层）

**现象**：无论服务器还是本机直连，GitHub Release 只有 30KB/s 左右。
**原因**：出口网络到 GitHub 的链路差，无代理。
**解法**：① 服务器开学术加速 `source /etc/network_turbo`；② 本地走代理 7897；③ 模型类走 ModelScope（国内 CDN，11MB/s）。
**教训**：**先测网速再动手**，别傻等；国内服务器下海外资源，ModelScope/HF 镜像/代理三选一。

### 坑 2：torchaudio 版本不匹配（依赖层）

**现象**：ComfyUI 启动报错 `OSError: libcudart.so.13: cannot open shared object file`。
**原因**：pip 默认装了最新版 torchaudio（对应 CUDA 13 runtime），而环境是 torch 2.8.0+cu128（CUDA 12.8，系统只有 libcudart.so.12）。ComfyUI 新版又**硬依赖 torchaudio**（音频生成功能），不能卸载。
**解法**：`pip install torchaudio==2.8.0`（与 torch 2.8.0 版本配对）。
**教训**：**torch 全家桶版本必须配对**（torch / torchvision / torchaudio 同版本号）；发现缺 so 库先 `find` 看系统有什么，再决定装哪个版本。

### 坑 3：pkill 自杀（运维层）

**现象**：`pkill -f "main.py --listen"` 后 SSH 连接立刻断开（exit 255），后续命令全没执行。
**原因**：**pkill -f 匹配的是完整命令行**——SSH 远程命令的 bash 命令行里也含 `"main.py --listen"` 这个字符串，把自己杀了。
**解法**：正则技巧 `pkill -f "[m]ain.py"`（方括号让自身命令行不匹配）。
**教训**：pkill -f 前先想清楚会不会匹配到自己的 shell；用 `[x]` 技巧是标准解法。

### 坑 4：ssh 非交互会话不加载 .bashrc

**现象**：`ssh seetacloud 'opencode'` 报 command not found，但登录后明明配置了 PATH。
**原因**：非交互式 SSH 只加载 `.profile`，不加载 `.bashrc`。
**解法**：交互登录正常使用；脚本里用 `bash -ic` 强制交互模式，或直接写全路径。
**教训**：**"登录能用"和"ssh 单命令能用"是两回事**，验证要模拟真实会话（ssh -t 或 bash -ic）。

### 坑 5：模型路径与格式（生态层）

**现象**：ModelScope 下载的模型是 diffusers 目录格式，ComfyUI 默认要单文件 checkpoint。
**解法**：ComfyUI 0.31 支持 `models/diffusers/` 目录 + `DiffusersLoader` 节点（标记 deprecated 但完全可用）；软链接零拷贝接入。
**教训**：新版本工具生态更新快，报错先查当前版本支持的格式，别按旧教程转格式。

## 批量生产方案（如何让 GPU 满负荷）

ComfyUI 常驻服务 + API 队列：一次提交 N 个 prompt（`POST /prompt`），自动排队执行，**模型只加载一次**。实测串行 8 张吞吐 1.33 张/秒，**10 分钟能出约 800 张**（LCM + 串行），batch=4 可到 2 张/秒。

参考脚本：`/root/comfy_batch.py`（服务器上），工作流构造逻辑见上文节点图。

## 访问 WebUI 的姿势

服务只监听 `127.0.0.1`（**没暴露公网**，8188 被公网扫到是安全隐患），本地用 SSH 隧道访问：

```
ssh -L 8188:127.0.0.1:8188 seetacloud   # 保持窗口
浏览器打开 http://localhost:8188        # 可视化拖节点
```

## 后续优化方向（未做，留待下次）

- **TensorRT 引擎**：ComfyUI-TensorRT 插件，把 UNet 编译成专用引擎，2080Ti 可再快 30-50%（Turing 架构支持）
- **更高画质**：换 SDXL（1024×1024 原生分辨率，效果升一档，7GB fp16，2080Ti 能跑）
- **batch 调参**：8/16 档位实测最优吞吐
- **接入 OpenCode**：让 AI 通过 API 驱动批量生成

## 关键文件索引（服务器 /root）

| 文件 | 作用 |
|------|------|
| `gen_image.py` | diffusers 直调单张生成 |
| `dl_model.py` | ModelScope 模型下载 |
| `comfy_test.py` | ComfyUI LCM vs 普通对比测试 |
| `comfy_batch.py` | 批量队列生成脚本 |
| `/root/autodl-tmp/ComfyUI/` | ComfyUI 本体（数据盘） |
| `/root/autodl-tmp/ComfyUI/output/` | 生成图片输出 |

## 总结一句话

**网络先行（测速+选源）→ diffusers 快速验证链路 → ComfyUI 做生产**；LCM 把 25 步压到 4 步，吞吐翻 3-5 倍质量不掉；三个坑（torchaudio 版本、pkill 自杀、非交互 .bashrc）全是"环境与工具版本"的隐性规则，记录在案下次直接绕开。
