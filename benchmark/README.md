# 生图模型交叉对比评测

> 一轮完整的「4 模型 × 2 工作流」交叉对比实验。2026-08，AutoDL 云 GPU（RTX 2080 Ti 11GB）。
> 可视化结果：打开 `benchmark.html`（浏览器）。

## 评测设计

- **统一提示词**（英文，SD 系与阿里系都友好）：`a cute shiba inu wearing a red beret sitting by a cafe window, warm golden light, cozy atmosphere, photorealistic, highly detailed`
- **统一负面提示词**：`blurry, low quality, deformed limbs, watermark, text`
- **统一 seed：42**（保证同模型不同工作流可对比）
- **评分方式**：外部视觉模型（Qwen-VL，deepseek-vision 通道）对每张图打 0-10 分（画质清晰度 + 主题符合度 + 细节质量）

## 矩阵与参数

| 模型（ID） | 工作流 | 步数 | cfg | 采样器 | 调度器 | 分辨率 |
|---|---|---|---|---|---|---|
| SD 1.5（`sd15`） | standard | 25 | 7.0 | euler | normal | 512×512 |
| | popular | 20 | 7.0 | dpmpp_2m | karras | 512×512 |
| SDXL 1.0（`sdxl`） | standard | 20 | 7.0 | euler | normal | 1024×1024 |
| | popular | 20 | 7.0 | dpmpp_2m | karras | 1024×1024 |
| Qwen-Image（`qwen-image`，GGUF Q3 量化） | standard | 30 | 4.0 | euler | karras | 1024×1024 |
| | popular | 12 | 1.0 | res_multistep | simple | 1280×1280 |
| Z-Image-Turbo（`z-image-turbo`，fp8） | standard | 8 | 1.0 | dpmpp_2m | karras | 1024×1024 |
| | popular | 8 | 3.0 | dpmpp_2m | karras | 1024×1024 |

- **standard** = 服务端默认参数（workflows.py 初始配置）
- **popular** = 网上流行/官方推荐（Qwen-Image 取自官方 example 蒸馏配置 res_multistep/simple；Z-Image-Turbo 取自官方推荐 cfg=3；SD 系用社区常用 dpmpp_2m+karras）

## 结果总表（评分 / 耗时）

| 模型 | standard | popular | 胜者 |
|---|---|---|---|
| SD 1.5 | **8.0** / 6s | 7.2 / 12s | standard |
| SDXL 1.0 | 9.3 / 23s | **9.5** / 34s | popular |
| Qwen-Image | 5.5 / 588s | **9.5** / 181s | ⭐ popular 完胜 |
| Z-Image-Turbo | **7.7** / 21s | 3.0 / 26s | standard |

（耗时 = 采样阶段耗时，Qwen-Image popular 为 1280² 分辨率下的 12 步）

## 关键发现（对生产配置有直接指导意义）

1. **Qwen-Image 应用官方蒸馏配置**：12 步 res_multistep/simple（1280²）评分 9.5，远超默认 30 步 cfg4 的 5.5 分，且快 3 倍。默认参数需更新。
2. **Z-Image-Turbo 锁 cfg=1**：官方推荐 cfg3 在该模型/该卡上严重过饱和（3.0 分），cfg1 正常（7.7 分）。不要用 cfg3。
3. **SDXL 最稳**：两个配置均 9.3+ 分，英文提示词下性价比最高（23s/张）。
4. **SD 1.5 仅作基准**：老模型稳定但上限低，适合低分辨率快速迭代。

## 文件清单

| 文件 | 说明 |
|---|---|
| `benchmark.html` | 可视化对比页（内嵌图片 + 评分 + 参数 + 耗时） |
| `results.json` | 原始结构化数据（任务 ID、状态、耗时、图片路径） |
| `images/*.png` | 8 张生成图，命名 `模型__工作流.png` |

## 复现方法

```bash
# 前置：本机 SSH 隧道已建（见 docs/server-status.md）
cd client
python3 benchmark.py          # 重新跑一遍矩阵（改 MATRIX 里的参数/提示词即可）
# 说明：评分/HTML 生成工具（tools/make_html.py）已移除；现有结论见 benchmark.html 与 results.json
```

相关文档：模型清单与部署现状见 `../docs/server-status.md`；API 见 `../docs/api.md`。
