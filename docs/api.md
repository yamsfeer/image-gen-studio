# 后端 API 参考

> 服务层（FastAPI）暴露的 HTTP API。所有请求走 nginx 8080 + Basic Auth。
> Base URL：`http://localhost:8080`（本机隧道）或 `http://<服务器>:8080`（若开公网）。
> 账号/密码在项目根 `.env`（`API_USER` / `API_PASSWORD`），默认账号 `comfy`。

## 认证

所有接口需带 Basic Auth 头：`Authorization: Basic base64(<API_USER>:<API_PASSWORD>)`
账号/密码来自项目根 `.env`（`API_USER` / `API_PASSWORD`）。

## POST /generate —— 提交生图任务

请求体（JSON）：

```json
{
  "model": "qwen-image",          // 必填：sd15 | sdxl | qwen-image | z-image-turbo
  "prompt": "一只猫",              // 必填
  "negative_prompt": "",          // 可选（z-image-turbo 不吃负向，传空）
  "width": 1024,                  // 256-2048，64 的倍数
  "height": 1024,
  "steps": 30,                    // 1-100
  "cfg": 4.0,                     // 1-20
  "seed": 42,                     // 缺省用时间戳
  "batch_size": 1,                // 1-4
  "sampler": "euler",             // 可选，覆盖模型默认（euler/dpmpp_2m/res_multistep...）
  "scheduler": "karras"           // 可选（normal/karras/simple...）
}
```

响应（立即返回，任务后台执行）：

```json
{"task_id": "dd875af1ea3343f9afb60ebea6e1f50f", "status": "queued", "prompt_id": "2754ba91-..."}
```

## GET /task/{task_id} —— 轮询任务状态

```json
{
  "task_id": "...",
  "model": "qwen-image",
  "status": "queued",             // submitted | queued | running | done | error
  "queue_position": 2,            // 排队位置（排队时）
  "progress": {"value": 7, "max": 30},  // 实时采样进度（运行时，WebSocket 推送）
  "images": ["/image/xxx?index=0"],     // 完成后的图片 URL（相对路径）
  "error": null,
  "elapsed_seconds": 160.1
}
```

## GET /image/{task_id}?index=0 —— 下载图片

返回 PNG 二进制。任务未完成返回 409。

## GET /stats —— 显卡与队列状态

```json
{
  "gpu": {"name": "NVIDIA GeForce RTX 2080 Ti", "memory_used_mb": 159, "memory_total_mb": 11264,
          "utilization_pct": 0, "temperature_c": 29},
  "queue": {"running": 0, "pending": 0},
  "active_tasks": 0, "total_tasks": 5
}
```

## GET /models —— 可用模型及默认参数

返回模型列表，含各模型默认参数（width/height/steps/cfg/sampler/scheduler）和说明。

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

## 客户端库（client/client.py）

已封装全部接口，Python 用法：

```python
from client import ImageClient
c = ImageClient.from_env()   # 从 .env / 环境变量读取 API_BASE / API_USER / API_PASSWORD
task = c.generate("qwen-image", "一只猫", steps=30, cfg=4.0)
st = c.wait(task["task_id"])          # 轮询到完成（默认 5s 间隔，30min 超时）
c.download(task["task_id"], "cat.png")
```

命令行用法见 README 和 server-status.md。
