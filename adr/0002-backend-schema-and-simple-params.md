# 0002 能力自省（/presets）+ 面向小白的参数简化

状态: 已接受
日期: 2026-08-14

## 背景 / 动机

基线（0001）里前端能力被锁死在「选模型 + 填提示词 + 下载」的最小闭环，参数写死在后端，
前端是硬编码预设。要让前端「活」起来，同时又不给小白用户堆学习成本，需要一个折中：

- **后端能力做全**：该有的参数接口都留着，字段可传、校验在后端。
- **前端暴露做窄**：默认只给用户看「模型 / 提示词 / 分辨率 / 宽高比」这几个他能懂的，
  其余（seed / LoRA / sampler / scheduler / 图生图等）一律用模型默认值，不渲染、不打扰。

## 决策

### 1. 新增 `GET /presets` —— 「前端表单数据源 + 能力开关」

前端据此动态渲染控件，不再硬编码。返回：宽高比预设、分辨率档位、能力开关（capabilities）。
接口名定为 `/presets`（不用 `/schema`，理由见 `adr/0003`）；完整返回结构见 `adr/0003`。

```json
{
  "aspect_ratios": [ { "id": "1:1", "label": "方形 1:1" }, "..." ],
  "resolutions":   [ { "value": 512, "label": "512（小）" }, "..." ],
  "capabilities": {
    "aspect_ratio": true, "resolution": true,
    "seed_control": false, "loras": false,
    "img2img": false, "inpaint": false, "upscale": false
  }
}
```

- `capabilities` 是核心：后端声明「我现在支持什么」，前端只渲染 `true` 的项，隐藏 `false` 的。
  以后放开 seed/LoRA/img2img 时，把对应 flag 翻 `true` + 加字段，前端自动出现。
- 每个模型的参数范围/档位不放在这里，而是挂在 `GET /models` 的 `params` 块里（模型自带的
  「参数说明」），两者职责分开。
- `resolutions` 按模型 VRAM（11GB）上限裁剪，超出 2048 或显存不安全的档位不返回。
- `aspect_ratios` 是固定预设，不放任意比例输入（避免小白纠结）。

### 2. `POST /tasks`（原 /generate）扩展 `aspect_ratio` + `resolution`

- 新增 `aspect_ratio`（预设 key）+ `resolution`（短边长度，64 的倍数），与显式
  `width`/`height` **三选一**（显式宽高 / 宽高比+分辨率 / 模型默认）。
- 后端计算宽高：`resolution` = 短边；长边 = `round(resolution × ratio / 64) × 64`，
  并做 `256 ≤ 边长 ≤ 2048` 校验。
- **seed 保持后端随机**（默认 `time.time()`，不暴露给新手）；`seed` 字段仍存在于任务模型里，
  便于高级用户/客户端直接传，但前端默认不渲染。
- **本次不新增**：LoRA、img2img、inpaint、upscale、sampler/scheduler 手动选择（记录于
  `docs/backlog.md`）。

### 3. 原则：「后端权威，前端从简」

- 参数校验全部在后端（沿用 0001 约束 3），前端只是渲染 `/presets` + `/models` 给出的合法选项。
- 前端默认 UI 只暴露 4 个输入：**模型、提示词、分辨率、宽高比**；高级项折叠或完全隐藏。

## 备选方案

- 不做自省接口，直接在前端写死选项 → **否决**：每加一个模型/档位都要改前端 + 重新部署。
- 自省接口与 `/models` 合并为一个 → 部分保留：`/models` 继续管「模型 + 参数定义」，
  `/presets` 管「全局预设 + 能力开关」，职责分开更清晰。
- 宽高比+分辨率算成固定 (width,height) 预设列表 → 备选，实现更简单但不够灵活；先按
  「比例 × 短边」做，前端仍可显示成预设。

## 影响 / 后果

- 前端可动态渲染分辨率/宽高比，零学习成本（只加两个他能看懂的选项）。
- 为后续放开 seed/LoRA/img2img 预留了 `capabilities` 开关。
- 代价：`/presets` 与 `server/workflows.py` 的模型注册表需保持同步，避免两端各自维护参数。

## 关联

- 前置：`adr/0001-backend-api-baseline.md`
- 接口路径与返回结构（命名决策）：`adr/0003-api-restful-refactor.md`
- 待办（本次不做）：`docs/backlog.md`
- 实现：`server/service.py`、`server/workflows.py`、`webui/`
