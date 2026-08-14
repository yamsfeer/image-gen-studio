# 0003 API 资源化重构：路径与返回结构

状态: 已接受
日期: 2026-08-14

## 背景 / 动机

0002 讨论中暴露出原命名的问题：

1. `/schema` 是开发者黑话，看不出它干什么、返回什么。
2. 动词/名词混用：`/generate`（动词）、`/task/{id}`（单数）、`/image/{id}`（单数）、`/models`（复数）。
3. 图片是任务的产出，却用 `/image/{task_id}?index=N` 这种带查询参数的写法，从属关系没表达出来。

因此把整组 API 重新整理：**资源化、复数、层级化**，每个接口返回自解释的数据。
已确认：**不加 `/v1` 前缀**（个人项目、前后端同仓、无外部调用方，一次改干净更划算）。

## 决策

### 端点总表（权威定义，实现以此为准）

| 方法 | 路径 | 做什么 | 前端用途 |
|---|---|---|---|
| `GET` | `/` | API 总览（版本 + 各资源链接） | 服务自检 |
| `GET` | `/presets` | 预设数据源：宽高比、分辨率档位 + capabilities 开关（见 0002） | 渲染分辨率/宽高比控件 |
| `GET` | `/models` | 模型目录，每个模型自带参数定义（defaults + params 范围） | 渲染模型下拉 + 参数控件 |
| `POST` | `/tasks` | 提交生图任务（原 `/generate`） | 「生成」按钮 |
| `GET` | `/tasks/{id}` | 任务状态 + 结果（进度/图片/参数/耗时） | 轮询进度 |
| `GET` | `/tasks/{id}/images` | 任务的图片列表 | 出图后展示 |
| `GET` | `/tasks/{id}/images/{index}` | 下载第 N 张图（PNG） | 下载按钮 |
| `GET` | `/status` | 服务状态：GPU + 队列 + 任务统计（原 `/stats`） | 页面顶栏状态 |

> 预留（backlog，路径按本设计，将来不加冲突）：`GET /tasks`（列表）、`POST /tasks/{id}/cancel`（取消）、
> `DELETE /tasks/{id}`（删除）、`GET /tasks/{id}/images` 已在表中。

### 返回结构（逐接口）

**`GET /`**

```json
{ "service": "image-service", "version": "1.1.0",
  "endpoints": { "presets": "/presets", "models": "/models", "tasks": "/tasks", "status": "/status" } }
```

**`GET /presets`** —— 前端下拉数据源 + 能力开关

```json
{ "aspect_ratios": [ {"id": "1:1", "label": "方形 1:1"}, {"id": "4:3", "label": "横版 4:3"},
                     {"id": "3:4", "label": "竖版 3:4"}, {"id": "16:9", "label": "横屏 16:9"},
                     {"id": "9:16", "label": "竖屏 9:16"} ],
  "resolutions": [ {"value": 512, "label": "512（小）"}, {"value": 768, "label": "768（中）"},
                   {"value": 1024, "label": "1024（大）"}, {"value": 1280, "label": "1280（仅 qwen-image）"} ],
  "capabilities": { "aspect_ratio": true, "resolution": true,
                    "seed_control": false, "loras": false,
                    "img2img": false, "inpaint": false, "upscale": false } }
```

**`GET /models`** —— 每个模型自带「参数说明」（params 块 = 滑杆/下拉的渲染依据）

```json
{ "models": [ { "id": "qwen-image", "name": "Qwen-Image (Q3_K_M, GGUF)",
    "description": "中文理解强；官方蒸馏配置，勿用高步数/高cfg",
    "defaults": { "width": 1280, "height": 1280, "steps": 12, "cfg": 1.0,
                  "sampler": "res_multistep", "scheduler": "simple" },
    "params": { "width":    {"type": "int",   "min": 256, "max": 2048, "step": 64},
                "height":   {"type": "int",   "min": 256, "max": 2048, "step": 64},
                "steps":    {"type": "int",   "min": 1,   "max": 100},
                "cfg":      {"type": "float", "min": 1.0, "max": 20.0},
                "sampler":  {"type": "select", "options": ["res_multistep", "euler", "dpmpp_2m", "ddim", "uni_pc"]},
                "scheduler": {"type": "select", "options": ["simple", "normal", "karras"]} } } ] }
```

**`POST /tasks`** —— 请求体三选一指定尺寸；响应带任务链接

```json
// 请求
{ "model": "qwen-image", "prompt": "一只猫", "negative_prompt": "",
  "aspect_ratio": "1:1", "resolution": 1024 }
// 或 {"width": 1024, "height": 1024}（显式宽高，与 aspect_ratio/resolution 互斥）
// 或都不传（用模型默认尺寸）

// 响应（201）
{ "task_id": "dd875af1ea3343f9afb60ebea6e1f50f", "status": "queued", "model": "qwen-image",
  "links": { "task": "/tasks/dd875af1ea3343f9afb60ebea6e1f50f",
             "images": "/tasks/dd875af1ea3343f9afb60ebea6e1f50f/images" } }
```

**`GET /tasks/{id}`** —— 状态 + 实际使用的参数（含真实 seed，可复现）

```json
{ "task_id": "...", "model": "qwen-image", "status": "running", "queue_position": 2,
  "progress": { "value": 7, "max": 12 },
  "params": { "width": 1024, "height": 1024, "steps": 12, "cfg": 1.0,
              "seed": 42, "sampler": "res_multistep", "scheduler": "simple" },
  "images": ["/tasks/.../images/0", "/tasks/.../images/1"],
  "error": null,
  "created_at": "2026-08-14T10:00:00+08:00", "finished_at": null, "elapsed_seconds": 12.3 }
```

**`GET /tasks/{id}/images`** —— 未完成时 `images` 为空，`status` 为当前任务状态

```json
{ "status": "done",
  "images": [ { "index": 0, "url": "/tasks/.../images/0",
                "width": 1024, "height": 1024, "filename": "qwen_image_00001_.png" } ] }
```

**`GET /tasks/{id}/images/{index}`** —— 返回 PNG 二进制（`Content-Disposition` 带文件名）

**`GET /status`**

```json
{ "service": { "status": "ok", "version": "1.1.0" },
  "comfyui": { "status": "ok" },
  "gpu": { "name": "NVIDIA GeForce RTX 2080 Ti", "memory_used_mb": 159,
           "memory_total_mb": 11264, "utilization_pct": 0, "temperature_c": 29 },
  "queue": { "running": 0, "pending": 1 },
  "tasks": { "active": 1, "total": 5 } }
```

### 规则

1. 路径一律复数资源，从属关系用层级：`/tasks/{id}/images/{index}`。
2. `POST /tasks` 返回 201 + `task_id` + `links`（前端无需拼 URL）。
3. 任务状态机不变（0001）：`submitted → queued → running → done/error`。
4. 不加 `/v1`；将来若确需 v2，再统一迁移，本次不为兼容留层。
5. 参数校验仍在后端；前端只渲染 `/presets` + `/models` 给的数据。

## 备选方案

- 轻量改（保留 `/generate` `/task/{id}` `/image/{id}`，只把 `/schema`→`/presets`、`/stats`→`/status`）
  → **否决**：风格不统一、层级不表达，迟早再改一次。
- 加 `/v1` 前缀 → **否决**：个人项目前后端同仓、无外部调用方，一次改干净更划算。
- 能力接口命名 `/options`、`/capabilities` → 讨论后定为 `/presets`（「预设」一听就是
  前端下拉的数据源，小白场景语义最直白）。

## 影响 / 后果

- 需同步改名：`server/service.py`（路由）、`client/client.py`（方法/路径）、`webui/handlers.py` + `webui/ui.py`、
  `docs/api.md`（重写）、`AGENTS.md`/`README.md` 引用；改完 `./deploy.sh` 部署。
- 无外部调用方，不做兼容层/双写。
- 客户端方法名对应：`presets()`、`models()`、`create_task()`、`get_task()`、
  `list_images()`、`download_image()`、`status()`。

## 关联

- 前置：`adr/0001-backend-api-baseline.md`、`adr/0002-backend-schema-and-simple-params.md`
- 待办（预留路径）：`docs/backlog.md`
- 实现：`server/service.py`、`server/workflows.py`、`client/client.py`、`webui/`
