# 04-ComfyUI与模型推理生态地图

> 2026-08 记录。从"不知道去哪找"到"知道全貌"：ComfyUI 生态 + 模型推理生态两张地图。

## 一句话总览

AI 生成的世界有两套并行生态：**模型推理生态**（TensorRT、蒸馏模型等，管"怎么跑得快/效果好"）和 **ComfyUI 生态**（管"怎么搭生成流程"）。ComfyUI 是两者的交汇点——它消费模型、加载工作流、插上推理加速插件。

## 一、ComfyUI 生态：三类资产各有自己的"下载站"

```
ComfyUI 的三类资产                去哪找（国内 → 国外）
──────────────────────            ────────────────────────────
模型 (checkpoint/LoRA/VAE)          ModelScope(魔搭) → HuggingFace / Civitai
工作流 (.json / 内嵌png)            B站/知乎教程 → comfyworkflows.com / Civitai / OpenArt
插件 (custom_nodes)                ComfyUI-Manager(应用商店) / GitHub 直接 clone
```

**模型**：国内首选 **ModelScope（魔搭）**——不用翻墙、速度块；国内还有 **LiblibAI（哩布哩布）** 是模型站。国外首选 **Civitai**（最流行，模型最全，附带工作流和 LoRA），HuggingFace 是技术原产地。

**工作流**：ComfyUI 工作流是 JSON 文件，有两种形态——`.json` 文件，或**内嵌在工作流截图的 png 里**（拖进 WebUI 自动还原节点图）。获取渠道：

- **comfyworkflows.com**——最大的工作流分享站，有预览图、一键下载、注明依赖的模型
- **Civitai / OpenArt.ai**——模型站但工作流丰富
- **GitHub**——大神合集仓库（如 ZHO-ZHO-ZHO 的工作流合集）
- **Reddit r/comfyui / B站 / 知乎**——社区讨论和教程分享

**插件**：核心入口是 **ComfyUI-Manager（ltdrdata 出品）**——插件的"应用商店"，装一个它就等于有了整个插件的搜索/安装/更新面板，新手第一件事应该是装它。进阶是 GitHub 直接 clone 到 `custom_nodes/` 目录。

## 二、模型推理生态：加速工具的完整谱系

加速手段分两大流派，**改模型（蒸馏）远比改框架（kernel）划算**：

```
流派         工具                   原理                   2080Ti 能用？
─────────    ──────────────────     ───────────────────    ─────────
编译引擎      TensorRT              算子融合+自动调优        ✅ 但要修插件兼容
            torch.compile          PyTorch 内置图编译       ✅ 一行代码
kernel优化    SageAttention         注意力量化+优化 kernel   ⚠️ Turing太老不推荐
            xFormers               内存优化注意力            ✅ 旧方案已被内置替代
            FlashAttention         注意力 kernel            ✅ torch 2.x 已内置
模型蒸馏      LCM / Turbo/Schnell   25步→4-8步出图           ✅ 最实用(我们已用LCM)
```

**TensorRT** 是英伟达官方王牌推理框架，至今仍是 SD 加速第一梯队——社区公认的"编译引擎"代表，把模型编译成高度优化的可执行引擎。**SageAttention** 是 2024 年清华团队的注意力 kernel 优化（类 FlashAttention 思路），Ampere 及以上架构（30系后）效果显著，但 2080Ti（Turing）不支持官方 CUDA 内核，只能走降级路径，收益打折。

**蒸馏模型（LCM/Turbo）** 是社区公认性价比之王：不动底层框架，把采样步数从 25-30 砍到 4-8，直接 3-6 倍提速，效果还接近——我们已在 ComfyUI 里用 LCM-LoRA 实现了 0.75s/张。

## 三、同行们实际在用什么（2026 年社区常态）

- **日常主力**：ComfyUI + SDXL 系模型 + Civitai 下模型 + ComfyUI-Manager 管插件
- **追求画质**：FLUX.1（需 24GB 显存，2080Ti 跑不动）
- **追求速度**：SDXL-Turbo / LCM / 量化版模型
- **生成视频**：AnimateDiff（轻量，能跑）→ 进阶 Wan 2.x / 可灵（需大显存）

## 四、我们的当前资产（2026-08 状态）

```
已跑通: SD1.5 出图(2s) / SDXL 出图(16s, 8.5分) / AnimateDiff 视频(40s/16帧)
加速:   LCM-LoRA 4步出图(0.75s/张) 批量 1.33张/秒
模型:   SD1.5 fp16 / SDXL fp16(diffusers+单文件) / AnimateDiff motion / LCM-LoRA
插件:   ComfyUI_TensorRT(兼容坑放弃) / AnimateDiff-Evolved
工作流: 官方示例(sdxl/video/lcm) + ZHO合集 + 手写最小工作流
待装:   ComfyUI-Manager(插件应用商店, 下一步)
```
