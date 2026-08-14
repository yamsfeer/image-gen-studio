# 后端 API 参考（前后端契约）

> **这是前后端之间唯一的接口契约**。前端改版/开发只依据本文档 + `adr/0003-api-restful-refactor.md`，
> 不再参考旧代码里的调用方式。
>
> 服务层（FastAPI）暴露的 HTTP API，**资源化 REST 设计**。所有请求走 nginx 8080 + Basic Auth。
> Base URL：`http://localhost:8080`（本机 SSH 隧道）或 `http://<服务器>:8080`（若开公网）。
> 账号/密码在项目根 `.env`（`API_USER` / `API_PASSWORD`），默认账号 `comfy`。
>
> 交互式调试：浏览器打开 `http://localhost:8080/docs`（Swagger UI，需 Basic Auth），
> 机器可读定义：`http://localhost:8080/openapi.json`。

## 1. 通用约定

### 认证

所有接口（含图片下载）都需要 Basic Auth 头：

```
Authorization: Basic base64(<API_USER>:<API_PASSWORD>)
```

前端 fetch 示例：

```js
const headers = { Authorization: "Basic " + btoa(API_USER + ":" + API_PASSWORD) };
```

### 请求 / 响应格式

- 请求体：JSON，`Content-Type: application/json`。
- 响应体：JSON（`/tasks/{id}/images/{index}` 除外，返回 PNG 二进制）。
- 所有时间字段为 ISO 8601 字符串（含时区偏移，如 `2026-08-14T10:00:00+08:00`）。
- `elapsed_seconds` 为任务已耗时（完成前为累计耗时，完成后为总耗时）。

### 错误响应格式（重要，前端需按此处理）

| 状态码 | 含义 | 响应体 |
|---|---|---|
| `400` | 业务参数不合法 | `{"detail": "中文错误说明"}`（字符串） |
| `404` | 资源不存在（任务/图片） | `{"detail": "任务不存在"}` |
| `409` | 任务未完成，无图片可下载 | `{"detail": "任务未完成，无图片可下载"}` |
| `422` | 请求体缺失/类型错/JSON 非法（pydantic 校验失败） | `{"detail": [{"type": "...", "loc": [...], "msg": "...", "input": ...}]}`（数组，可按 loc 定位到具体字段） |
| `502` | 从 ComfyUI 读取图片失败 | `{"detail": "..."}` |

> 前端提示策略：`400/404/409` 直接展示 `detail` 字符串；`422` 解析 `detail` 数组，
> 把 `loc` 里最后一个字段名 + `msg` 拼成可读提示；其他状态码（如 401/403）按网络/认证错误处理。

### 端点总览

| 方法 | 路径 | 做什么 | 前端用途 |
|---|---|---|---|
| `GET` | `/` | API 总览（版本 + 资源链接） | 服务自检 |
| `GET` | `/presets` | 预设数据源：宽高比、分辨率 + capabilities | 渲染分辨率/宽高比控件 |
| `GET` | `/models` | 模型目录（默认参数 + 参数定义） | 渲染模型下拉 + 参数控件 |
| `POST` | `/tasks` | 提交生图任务 | 「生成」按钮 |
| `GET` | `/tasks/{task_id}` | 任务状态 + 结果 | 轮询进度 |
| `GET` | `/tasks/{task_id}/images` | 任务产出的图片列表 | 出图后展示 |
| `GET` | `/tasks/{task_id}/images/{index}` | 下载第 N 张图（PNG） | 下载按钮 |
| `GET` | `/status` | 服务 / GPU / 队列状态 | 页面状态栏 |

> 预留（未实现，见 `docs/backlog.md`）：`GET /tasks`（列表）、`POST /tasks/{id}/cancel`（取消）、
> `DELETE /tasks/{id}`（删除）。

## 2. 端点详述

### GET / —— API 总览

```json
{"service": "image-service", "version": "1.1.0",
 "endpoints": {"presets": "/presets", "models": "/models", "tasks": "/tasks", "status": "/status"}}
```

```bash
curl -u comfy:密码 http://localhost:8080/
```

### GET /presets —— 前端表单数据源

返回前端可选的预设值 + 能力开关。**前端只渲染 `capabilities` 为 `true` 的项**，`false` 的项不显示任何控件。

```json
{
  "aspect_ratios": [
    {"id": "1:1",  "label": "方形 1:1"},
    {"id": "4:3",  "label": "横版 4:3"},
    {"id": "3:4",  "label": "竖版 3:4"},
    {"id": "16:9", "label": "横屏 16:9"},
    {"id": "9:16", "label": "竖屏 9:16"}
  ],
  "resolutions": [
    {"value": 512,  "label": "512（小）"},
    {"value": 768,  "label": "768（中）"},
    {"value": 1024, "label": "1024（大）"},
    {"value": 1280, "label": "1280（大图，较慢）"}
  ],
  "capabilities": {
    "aspect_ratio": true, "resolution": true,
    "seed_control": false, "loras": false,
    "img2img": false, "inpaint": false, "upscale": false
  }
}
```

字段说明：

- `aspect_ratios`：宽高比预设。`id` 是传给 `/tasks` 的值，`label` 用于展示。
- `resolutions`：分辨率档位 = **短边长度**（64 的倍数）。`value` 传给 `/tasks`。
- `capabilities`：能力开关。`true` = 前端应渲染对应控件（如 `aspect_ratio`、`resolution`）；
  `false` = 前端不渲染（如 `seed_control`、`loras` 等，当前后端不支持）。

### GET /models —— 模型目录

每个模型自带 `defaults`（最佳参数，缺省时后端使用）和 `params`（参数定义，前端据此渲染滑杆/下拉）。

```json
{
  "models": [
    {
      "id": "qwen-image",
      "name": "Qwen-Image (Q3_K_M, GGUF)",
      "description": "中文理解强；默认=官方蒸馏配置，勿用高步数/高cfg",
      "defaults": {"width": 1280, "height": 1280, "steps": 12, "cfg": 1.0,
                   "sampler": "res_multistep", "scheduler": "simple"},
      "params": {
        "width":     {"type": "int",   "min": 256, "max": 2048, "step": 64},
        "height":    {"type": "int",   "min": 256, "max": 2048, "step": 64},
        "steps":     {"type": "int",   "min": 1,   "max": 100,  "step": 1},
        "cfg":       {"type": "float", "min": 1.0, "max": 20.0, "step": 0.5},
        "sampler":   {"type": "select", "options": ["euler", "euler_ancestral", "dpm_2", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "ddim", "uni_pc", "res_multistep"]},
        "scheduler": {"type": "select", "options": ["normal", "karras", "simple", "sgm_uniform", "ddim_uniform"]}
      }
    }
  ]
}
```

字段说明：

- `params` 里 `type: "int"|"float"` 的字段带 `min`/`max`/`step`（滑杆）；`type: "select"` 带 `options`（下拉）。
- 前端默认只暴露模型/提示词/分辨率/宽高比即可；`steps/cfg/sampler/scheduler/seed` 属于高级参数，
  当前按「面向小白」原则不渲染（但字段仍然可用，见 §6）。

### POST /tasks —— 提交生图任务

**请求体（JSON）**：

```json
{
  "model": "qwen-image",        // 必填：sd15 | sdxl | qwen-image | z-image-turbo（来自 /models）
  "prompt": "一只猫",            // 必填，非空
  "negative_prompt": "",        // 可选（z-image-turbo 为蒸馏模型，不支持负面提示词，传空即可）
  "aspect_ratio": "1:1",        // 可选：/presets 里的 id；与 resolution 成对
  "resolution": 1024,           // 可选：短边长度，64 的倍数
  "width": null,                // 可选：显式宽高（与 aspect_ratio/resolution 互斥，二选一）
  "height": null,
  "steps": null,                // 可选：1-100，缺省用模型默认
  "cfg": null,                  // 可选：1.0-20.0，缺省用模型默认
  "seed": null,                 // 可选：缺省随机（时间戳）；任务响应里返回实际 seed 可复现
  "batch_size": 1,              // 可选：1-4
  "sampler": null,              // 可选：覆盖模型默认（来自 /models params.sampler.options）
  "scheduler": null             // 可选：覆盖模型默认（来自 /models params.scheduler.options）
}
```

**尺寸三选一规则**：

| 方式 | 传参 | 说明 |
|---|---|---|
| 宽高比+分辨率 | `aspect_ratio` + `resolution` | 后端按比例算长边（64 取整）；短边=resolution |
| 显式宽高 | `width` + `height` | 缺一个则用模型默认补 |
| 模型默认 | 都不传 | 用该模型的 `defaults`（如 qwen-image 1280×1280） |

> 注意：`aspect_ratio` 与 `width/height` 不能同时传（400）；`aspect_ratio`/`resolution` 必须成对（400）。
> 超限组合会被拒，例如 `resolution=1280` + `16:9` 长边约 2304 > 2048 → 400，前端可预先提示。

**响应（201，立即返回，任务后台执行）**：

```json
{"task_id": "dd875af1ea3343f9afb60ebea6e1f50f", "status": "queued", "model": "qwen-image",
 "links": {"task": "/tasks/dd875af1ea3343f9afb60ebea6e1f50f",
           "images": "/tasks/dd875af1ea3343f9afb60ebea6e1f50f/images"}}
```

- `status` 正常情况下是 `queued`；若提交到 ComfyUI 失败则为 `error`（此时轮询 `/tasks/{id}`
  的 `error` 字段有原因）。无论哪种都代表任务已创建，**继续轮询即可**。

```bash
curl -u comfy:密码 -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-image","prompt":"一只猫","aspect_ratio":"1:1","resolution":1024}'
```

### GET /tasks/{task_id} —— 轮询任务状态

```json
{
  "task_id": "dd875af1ea3343f9afb60ebea6e1f50f",
  "model": "qwen-image",
  "status": "running",                       // submitted | queued | running | done | error
  "queue_position": 2,                       // 仅排队时非空
  "progress": {"value": 7, "max": 12},       // 仅 running 时非空（当前步数/总步数）
  "params": {"width": 1024, "height": 1024, "steps": 12, "cfg": 1.0,
             "seed": 42, "batch_size": 1, "sampler": "res_multistep", "scheduler": "simple"},
  "images": ["/tasks/.../images/0", "/tasks/.../images/1"],  // done 后非空（相对路径）
  "error": null,                             // error 时非空
  "created_at": "2026-08-14T10:00:00+08:00",
  "finished_at": null,                       // done/error 后非空
  "elapsed_seconds": 12.3
}
```

- `images` 是**相对路径**，前端访问时需拼上 Base URL：`API_BASE + url`。
- 未知 task_id → 404。

### GET /tasks/{task_id}/images —— 任务图片列表

```json
{"status": "done",
 "images": [{"index": 0, "url": "/tasks/.../images/0",
             "width": 1024, "height": 1024, "filename": "qwen_image_00001_.png"}]}
```

任务未完成时：`status` 为当前状态、`images` 为空数组。

### GET /tasks/{task_id}/images/{index} —— 下载图片

返回 PNG 二进制（`Content-Type: image/png`）。

- 任务未完成 → 409；`index` 越界 → 400；未知 task_id → 404。

```bash
curl -u comfy:密码 http://localhost:8080/tasks/<id>/images/0 -o out.png
```

> 前端注意：`<img src>` 无法携带 Basic Auth 头。请用 `fetch(url, {headers})` → `blob()` →
> `URL.createObjectURL()` 的方式显示和下载图片。

### GET /status —— 服务 / GPU / 队列状态

```json
{
  "service": {"status": "ok", "version": "1.1.0"},
  "comfyui": {"status": "ok"},               // ComfyUI 不可达时为 "error"
  "gpu": {"name": "NVIDIA GeForce RTX 2080 Ti", "memory_used_mb": 159,
          "memory_total_mb": 11264, "utilization_pct": 0, "temperature_c": 29},
  "queue": {"running": 0, "pending": 1},
  "tasks": {"active": 1, "total": 5}
}
```

`gpu` 在无 nvidia-smi 时返回 `{"error": "nvidia-smi 不可用"}`（正常服务器不会出现）。

## 3. 任务状态机与轮询

```
submitted → queued → running → done
                        └─────→ error
```

- `submitted`：任务刚创建，一瞬间就转 `queued`（提交 ComfyUI 成功）。
- `queued`：在 ComfyUI 队列中等待，`queue_position` = 排队位置（1 开始）。
- `running`：正在采样，`progress` = `{value, max}`（当前步/总步数）。
- `done`：完成，`images` 非空，`finished_at` 有值。
- `error`：失败，`error` 字段有原因；提交阶段失败也会落在这里。

**轮询建议**：每 2-3 秒调一次 `GET /tasks/{id}`，`status` 为 `done` 或 `error` 时停止。
出图耗时参考（RTX 2080 Ti）：qwen-image 1280² 约 1-3 分钟，z-image-turbo/sdxl 约 20-60 秒，
sd15 最快。

## 4. capabilities 机制（前端渲染规则）

`GET /presets` 的 `capabilities` 是「后端当前支持什么」的权威声明，前端**只渲染 `true` 的项**：

| flag | 当前值 | 前端行为 |
|---|---|---|
| `aspect_ratio` | `true` | 渲染宽高比选择 |
| `resolution` | `true` | 渲染分辨率选择 |
| `seed_control` | `false` | 不渲染 seed 输入（后端随机） |
| `loras` | `false` | 不渲染 LoRA 选择 |
| `img2img` / `inpaint` / `upscale` | `false` | 不渲染图生图/重绘/放大 |

以后后端放开新能力时只改 `capabilities` 和相关字段，前端无需改逻辑，按 flag 自动出现控件。
因此前端不要硬编码「哪些控件存在」，一律读 `/presets`。

## 5. 前端接入指南（数据驱动完整流程）

1. **加载表单**：并行调 `GET /presets` + `GET /models`。
   - 模型下拉 ← `models[].id` + `name`（description 做 tooltip）
   - 宽高比 ← `presets.aspect_ratios`（capabilities.aspect_ratio 为 true 时）
   - 分辨率 ← `presets.resolutions`（capabilities.resolution 为 true 时）
2. **提交**：`POST /tasks`，body 按 §2 三选一规则拼。
   - 选中的模型切换时，可用该模型 `defaults` 做默认值回显（如 qwen-image 默认 1280）。
   - 提交成功后拿 `task_id`，进入轮询。
3. **轮询**：每 2-3s `GET /tasks/{id}` 直到 `done`/`error`；期间展示 `progress`、`queue_position`。
4. **展示**：`done` 后，用 `images` 的相对 URL 拼 `API_BASE`，`fetch` 带 Basic Auth 转 blob 显示
   （或用 `GET /tasks/{id}/images` 拿图片元数据）。
5. **下载**：同 blob 方式触发保存。
6. **错误**：`400/404/409` 展示 `detail`；`422` 解析 detail 数组定位字段；请求异常提示网络/认证问题。
7. **状态栏**：每 10s `GET /status` 显示 GPU 占用/温度/队列长度；`comfyui.status == "error"` 时提示服务异常。

## 6. 参数速查

| 字段 | 类型 | 必填 | 范围/取值 | 缺省 |
|---|---|---|---|---|
| `model` | string | 是 | 见 `/models` | — |
| `prompt` | string | 是 | 非空 | — |
| `negative_prompt` | string | 否 | — | `""` |
| `aspect_ratio` | string | 否¹ | `/presets` 的 id | — |
| `resolution` | int | 否¹ | 256-2048，64 的倍数 | — |
| `width` / `height` | int | 否² | 256-2048，64 的倍数 | 模型默认 |
| `steps` | int | 否 | 1-100 | 模型默认 |
| `cfg` | float | 否 | 1.0-20.0 | 模型默认 |
| `seed` | int | 否 | 任意整数 | 随机（时间戳） |
| `batch_size` | int | 否 | 1-4 | 1 |
| `sampler` / `scheduler` | string | 否 | `/models` params.options | 模型默认 |

¹ `aspect_ratio` 与 `resolution` 必须成对；² 与 ¹ 互斥。

各模型默认参数（`/models` 的 `defaults`，前端可据此回显）：

| 模型 | width×height | steps | cfg | sampler | scheduler |
|---|---|---|---|---|---|
| qwen-image | 1280×1280 | 12 | 1.0 | res_multistep | simple |
| z-image-turbo | 1024×1024 | 8 | 1.0 | dpmpp_2m | karras |
| sdxl | 1024×1024 | 20 | 7.0 | euler | normal |
| sd15 | 512×512 | 25 | 7.0 | euler | normal |

> 这些是实测最佳参数（见 docs/parameter-guide.md），前端不要随意覆盖；高级参数控件默认不渲染。

## 7. 关于 ComfyUI 原生端点

ComfyUI 的 `/system_stats`、`/queue`、`/prompt`、`/view`、`/object_info` 等原生端点
**未通过 nginx 对外暴露**（nginx 只反代 FastAPI:8190）。ComfyUI(8188) 只监听 127.0.0.1，
由服务层内部直连，前端永远不需要也不应该直接访问 ComfyUI。

## 8. 设计文档

- 命名与返回结构（权威定义）：`adr/0003-api-restful-refactor.md`
- 能力开关与参数简化：`adr/0002-backend-schema-and-simple-params.md`
- 基线盘点：`adr/0001-backend-api-baseline.md`

## 9. 客户端库（client/client.py）

> 改造中：`client/client.py` 仍调用旧接口（/generate /task /stats），**尚未**按本契约更新，
> 更新前请勿作为前端参考。前端以本文档为准。

更新后的 Python 用法（示例）：

```python
from client import ImageClient
c = ImageClient.from_env()          # 从 .env / 环境变量读取 API_BASE / API_USER / API_PASSWORD
presets = c.presets()               # 预设 + capabilities
models  = c.models()                # 模型目录
task    = c.create_task("qwen-image", "一只猫", aspect_ratio="1:1", resolution=1024)
st = c.wait(task["task_id"])        # 轮询到完成
c.download(task["task_id"], "cat.png")
```
