# 后端 API 参考

> 服务层（FastAPI）暴露的 HTTP API，**资源化 REST 设计**（决策见 `adr/0003`）。
> 所有请求走 nginx 8080 + Basic Auth。
> Base URL：`http://localhost:8080`（本机隧道）或 `http://<服务器>:8080`（若开公网）。
> 账号/密码在项目根 `.env`（`API_USER` / `API_PASSWORD`），默认账号 `comfy`。

## 认证

所有接口需带 Basic Auth 头：`Authorization: Basic base64(<API_USER>:<API_PASSWORD>)`

## 端点总览

| 方法 | 路径 | 做什么 |
|---|---|---|
| `GET` | `/` | API 总览（版本 + 资源链接） |
| `GET` | `/presets` | 预设数据源：宽高比、分辨率档位 + capabilities |
| `GET` | `/models` | 模型目录（默认参数 + 参数定义） |
| `POST` | `/tasks` | 提交生图任务 |
| `GET` | `/tasks/{task_id}` | 任务状态 + 结果 |
| `GET` | `/tasks/{task_id}/images` | 任务产出的图片列表 |
| `GET` | `/tasks/{task_id}/images/{index}` | 下载第 N 张图 |
| `GET` | `/status` | 服务 / GPU / 队列状态 |

> 预留（未实现，见 `docs/backlog.md`）：`GET /tasks`（列表）、`POST /tasks/{id}/cancel`（取消）、
> `DELETE /tasks/{id}`（删除）。

## GET / —— API 总览

```json
{"service": "image-service", "version": "1.1.0",
 "endpoints": {"presets": "/presets", "models": "/models", "tasks": "/tasks", "status": "/status"}}
```

## GET /presets —— 前端表单数据源

返回前端可选的预设值 + 能力开关（前端只渲染 `capabilities` 为 `true` 的项）：

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

## GET /models —— 模型目录

每个模型自带 `defaults`（最佳参数，勿乱改，见 docs/parameter-guide.md）和 `params`（参数定义，
`int/float` 带 min/max/step，`select` 带 options，前端据此渲染滑杆/下拉）：

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

## POST /tasks —— 提交生图任务

请求体（JSON）。尺寸**三选一**：显式 `width`/`height` | `aspect_ratio`+`resolution` | 都不传（模型默认）：

```json
{
  "model": "qwen-image",        // 必填：sd15 | sdxl | qwen-image | z-image-turbo
  "prompt": "一只猫",            // 必填
  "negative_prompt": "",        // 可选
  "aspect_ratio": "1:1",        // 可选：/presets 里的 id；与 resolution 成对
  "resolution": 1024,           // 可选：短边长度，64 的倍数；1280+16:9 会超限被拒
  "width": null,                // 可选：显式宽高（与 aspect_ratio/resolution 互斥）
  "height": null,
  "steps": null,                // 可选：缺省用模型默认（如 qwen-image 12）
  "cfg": null,                  // 可选：缺省用模型默认（如 qwen-image 1.0）
  "seed": null,                 // 可选：缺省随机（时间戳）；任务里返回实际 seed 可复现
  "batch_size": 1,              // 1-4
  "sampler": null,              // 可选：覆盖模型默认
  "scheduler": null             // 可选：覆盖模型默认
}
```

响应（201，立即返回，任务后台执行）：

```json
{"task_id": "dd875af1ea3343f9afb60ebea6e1f50f", "status": "queued", "model": "qwen-image",
 "links": {"task": "/tasks/dd875af1ea3343f9afb60ebea6e1f50f",
           "images": "/tasks/dd875af1ea3343f9afb60ebea6e1f50f/images"}}
```

## GET /tasks/{task_id} —— 轮询任务状态

```json
{
  "task_id": "dd875af1ea3343f9afb60ebea6e1f50f",
  "model": "qwen-image",
  "status": "running",             // submitted | queued | running | done | error
  "queue_position": 2,             // 排队位置（排队时）
  "progress": {"value": 7, "max": 12},   // 实时采样进度
  "params": {"width": 1024, "height": 1024, "steps": 12, "cfg": 1.0,
             "seed": 42, "batch_size": 1, "sampler": "res_multistep", "scheduler": "simple"},
  "images": ["/tasks/.../images/0"],     // 完成后的图片 URL（相对路径）
  "error": null,
  "created_at": "2026-08-14T10:00:00+08:00",
  "finished_at": null,
  "elapsed_seconds": 12.3
}
```

## GET /tasks/{task_id}/images —— 任务图片列表

```json
{"status": "done",
 "images": [{"index": 0, "url": "/tasks/.../images/0",
             "width": 1024, "height": 1024, "filename": "qwen_image_00001_.png"}]}
```

任务未完成时 `status` 为当前状态、`images` 为空列表。

## GET /tasks/{task_id}/images/{index} —— 下载图片

返回 PNG 二进制。任务未完成返回 409，index 越界返回 400。

## GET /status —— 服务 / GPU / 队列状态

```json
{
  "service": {"status": "ok", "version": "1.1.0"},
  "comfyui": {"status": "ok"},
  "gpu": {"name": "NVIDIA GeForce RTX 2080 Ti", "memory_used_mb": 159,
          "memory_total_mb": 11264, "utilization_pct": 0, "temperature_c": 29},
  "queue": {"running": 0, "pending": 1},
  "tasks": {"active": 1, "total": 5}
}
```

## 状态机

```
submitted → queued → running → done
                        └─────→ error
```

## 关于 ComfyUI 原生端点

ComfyUI 的 `/system_stats`、`/queue`、`/prompt`、`/view`、`/object_info` 等原生端点
**当前未通过 nginx 对外暴露**（nginx 只反代 FastAPI:8190）。ComfyUI(8188) 只监听
127.0.0.1，由服务层（service.py 里的 `COMFY = "http://127.0.0.1:8188"`）内部直连，
外部无法直接访问。

## 设计文档

- 命名与返回结构：`adr/0003-api-restful-refactor.md`（权威定义）
- 能力开关与参数简化：`adr/0002-backend-schema-and-simple-params.md`
- 基线盘点：`adr/0001-backend-api-baseline.md`

## 客户端库（client/client.py）

> 改造中：client.py 仍调用旧接口（/generate /task /stats），需按本文件同步更新后才能使用。

封装全部接口的 Python 用法（更新后）：

```python
from client import ImageClient
c = ImageClient.from_env()          # 从 .env / 环境变量读取 API_BASE / API_USER / API_PASSWORD
presets = c.presets()               # 预设 + capabilities
models  = c.models()                # 模型目录
task    = c.create_task("qwen-image", "一只猫", aspect_ratio="1:1", resolution=1024)
st = c.wait(task["task_id"])        # 轮询到完成
c.download(task["task_id"], "cat.png")
```
