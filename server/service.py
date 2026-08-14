"""生图服务：包装 ComfyUI 后端的 HTTP API（资源化 REST，设计见 adr/0003）

- GET  /                              API 总览（版本 + 资源链接）
- GET  /presets                       预设数据源：宽高比/分辨率 + capabilities
- GET  /models                        模型目录（defaults + params 参数定义）
- POST /tasks                         提交生图任务（异步，返回 task_id + links）
- GET  /tasks/{task_id}               轮询任务状态
- GET  /tasks/{task_id}/images        任务产出的图片列表
- GET  /tasks/{task_id}/images/{index} 下载第 N 张图（PNG）
- GET  /status                        服务/GPU/队列状态
"""
import asyncio, json, subprocess, time, uuid
from datetime import datetime
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from workflows import MODELS, PARAMS, ASPECT_RATIOS, RESOLUTIONS, CAPABILITIES

COMFY = "http://127.0.0.1:8188"
CLIENT_ID = "image-service-" + uuid.uuid4().hex[:8]  # WebSocket 进度监听用同一个 client_id
VERSION = "1.1.0"

app = FastAPI(title="Image Service", version=VERSION)

# ---------------- 任务注册表 ----------------
TASKS: dict[str, dict] = {}

# ---------------- ComfyUI HTTP 客户端 ----------------
def comfy_get(path: str, timeout=15) -> dict:
    r = requests.get(COMFY + path, timeout=timeout)
    r.raise_for_status()
    return r.json()

def comfy_post(path: str, data: dict, timeout=30) -> dict:
    r = requests.post(COMFY + path, json=data, timeout=timeout)
    r.raise_for_status()
    return r.json()

def comfy_get_binary(path: str, timeout=30) -> bytes:
    r = requests.get(COMFY + path, timeout=timeout)
    r.raise_for_status()
    return r.content

# ---------------- WebSocket 实时进度监听 ----------------
async def ws_progress_listener():
    """监听 ComfyUI 的进度/状态推送，实时更新任务进度"""
    import websockets
    uri = f"ws://127.0.0.1:8188/ws?clientId={CLIENT_ID}"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    data = msg.get("data") or {}
                    pid = data.get("prompt_id")
                    if not pid:
                        continue
                    task = next((t for t in TASKS.values() if t.get("prompt_id") == pid), None)
                    if not task:
                        continue
                    t = msg.get("type")
                    if t == "progress":
                        task["progress"] = {"value": data.get("value"), "max": data.get("max")}
                    elif t == "execution_start":
                        task["status"] = "running"
                    elif t == "execution_success":
                        task["status"] = "done"
                    elif t == "execution_error":
                        task["status"] = "error"
                        task["error"] = str(data)[:500]
        except Exception:
            await asyncio.sleep(3)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(ws_progress_listener())

# ---------------- 参数模型 ----------------
class CreateTaskRequest(BaseModel):
    model: str = "qwen-image"
    prompt: str = Field(..., min_length=1)
    negative_prompt: str = ""
    # 尺寸三选一：width/height（显式）| aspect_ratio+resolution（预设）| 都不传（模型默认）
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[int] = None  # 短边长度，64 的倍数
    steps: Optional[int] = None       # 缺省用模型默认
    cfg: Optional[float] = None
    seed: Optional[int] = None        # 缺省随机（时间戳）
    batch_size: int = 1
    sampler: Optional[str] = None     # 覆盖模型默认采样器
    scheduler: Optional[str] = None   # 覆盖模型默认调度器

# ---------------- 工具 ----------------
def _round64(x: float) -> int:
    return int(round(x / 64) * 64)

def _iso(epoch: Optional[float]) -> Optional[str]:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch).astimezone().isoformat()

def _ratio_wh(ratio_id: str, resolution: int) -> tuple[int, int]:
    """按预设宽高比 + 短边长度计算 (width, height)。"""
    for r in ASPECT_RATIOS:
        if r["id"] == ratio_id:
            w, h = r["ratio"]
            break
    else:
        raise HTTPException(400, f"未知宽高比: {ratio_id}，可选: {[r['id'] for r in ASPECT_RATIOS]}")
    if w >= h:  # 横版/方形：短边是 height
        return _round64(resolution * w / h), resolution
    return resolution, _round64(resolution * h / w)  # 竖版：短边是 width

def _resolve_size(req: CreateTaskRequest) -> tuple[int, int]:
    """解析并校验尺寸（三选一），返回 (width, height)。"""
    explicit = req.width is not None or req.height is not None
    preset = req.aspect_ratio is not None or req.resolution is not None
    if explicit and preset:
        raise HTTPException(400, "width/height 与 aspect_ratio/resolution 二选一，不能同时传")
    defaults = MODELS[req.model]["defaults"]
    if preset:
        if req.aspect_ratio is None or req.resolution is None:
            raise HTTPException(400, "aspect_ratio 与 resolution 需成对提供")
        if not (256 <= req.resolution <= 2048 and req.resolution % 64 == 0):
            raise HTTPException(400, f"resolution 需为 256-2048 且是 64 的倍数，收到 {req.resolution}")
        w, h = _ratio_wh(req.aspect_ratio, req.resolution)
    elif explicit:
        w = req.width if req.width is not None else defaults["width"]
        h = req.height if req.height is not None else defaults["height"]
    else:
        w, h = defaults["width"], defaults["height"]
    for name, v in (("width", w), ("height", h)):
        if not (256 <= v <= 2048):
            raise HTTPException(400, f"{name}={v} 超出范围 256-2048")
        if v % 64:
            raise HTTPException(400, f"{name}={v} 需为 64 的倍数")
    return w, h

def _task_view(task: dict) -> dict:
    """任务 → 对外 JSON（内部存 epoch 时间戳，对外转 ISO）。"""
    elapsed = (task.get("finished_at") or time.time()) - task["created_at"]
    return {
        "task_id": task["task_id"],
        "model": task["model"],
        "status": task["status"],
        "queue_position": task["queue_position"],
        "progress": task["progress"],
        "params": task["params"],
        "images": [f"/tasks/{task['task_id']}/images/{i}" for i in range(len(task["images"]))],
        "error": task["error"],
        "created_at": _iso(task["created_at"]),
        "finished_at": _iso(task.get("finished_at")),
        "elapsed_seconds": round(elapsed, 1),
    }

# ---------------- 接口 ----------------
@app.get("/")
def root():
    return {"service": "image-service", "version": VERSION,
            "endpoints": {"presets": "/presets", "models": "/models",
                          "tasks": "/tasks", "status": "/status"}}

@app.get("/presets")
def presets():
    return {
        "aspect_ratios": [{"id": r["id"], "label": r["label"]} for r in ASPECT_RATIOS],
        "resolutions": RESOLUTIONS,
        "capabilities": CAPABILITIES,
    }

@app.get("/models")
def list_models():
    return {"models": [
        {"id": k, "name": m["name"], "description": m.get("description", ""),
         "defaults": m["defaults"], "params": PARAMS}
        for k, m in MODELS.items()]}

@app.post("/tasks", status_code=201)
def create_task(req: CreateTaskRequest):
    if req.model not in MODELS:
        raise HTTPException(400, f"未知模型: {req.model}，可用: {list(MODELS)}")
    if not req.prompt.strip():
        raise HTTPException(400, "prompt 不能为空")
    if not (1 <= req.batch_size <= 4):
        raise HTTPException(400, "batch_size 需在 1-4")

    defaults = MODELS[req.model]["defaults"]
    width, height = _resolve_size(req)
    steps = req.steps if req.steps is not None else defaults["steps"]
    cfg = req.cfg if req.cfg is not None else defaults["cfg"]
    if not (1 <= steps <= 100):
        raise HTTPException(400, f"steps={steps} 超出范围 1-100")
    if not (1.0 <= cfg <= 20.0):
        raise HTTPException(400, f"cfg={cfg} 超出范围 1-20")
    seed = req.seed if req.seed is not None else int(time.time())
    sampler = req.sampler or defaults.get("sampler", "euler")
    scheduler = req.scheduler or defaults.get("scheduler", "normal")

    task_id = uuid.uuid4().hex
    task = {
        "task_id": task_id,
        "model": req.model,
        "prompt": req.prompt,
        "params": {"width": width, "height": height, "steps": steps, "cfg": cfg,
                   "seed": seed, "batch_size": req.batch_size,
                   "sampler": sampler, "scheduler": scheduler},
        "status": "submitted",   # submitted → queued → running → done/error
        "progress": None,
        "queue_position": None,
        "images": [],
        "error": None,
        "prompt_id": None,
        "created_at": time.time(),
        "finished_at": None,
    }
    TASKS[task_id] = task

    try:
        workflow = MODELS[req.model]["builder"](
            req.prompt, req.negative_prompt, width, height,
            steps, cfg, seed, req.batch_size, sampler, scheduler)
        r = comfy_post("/prompt", {"prompt": workflow, "client_id": CLIENT_ID})
        task["prompt_id"] = r["prompt_id"]
        task["status"] = "queued"
    except Exception as e:
        task["status"] = "error"
        task["error"] = f"提交到 ComfyUI 失败: {e}"

    return {"task_id": task_id, "status": task["status"], "model": req.model,
            "links": {"task": f"/tasks/{task_id}", "images": f"/tasks/{task_id}/images"}}

def _refresh_status(task: dict):
    """从 ComfyUI 实时刷新任务状态（排队位置/完成/错误/图片）"""
    try:
        h = comfy_get(f"/history/{task['prompt_id']}", timeout=10)
    except Exception:
        return
    if task["prompt_id"] in h:
        entry = h[task["prompt_id"]]
        status_str = entry.get("status", {}).get("status_str")
        if status_str == "error":
            task["status"] = "error"
            msgs = entry.get("status", {}).get("messages", [])
            task["error"] = json.dumps(msgs, ensure_ascii=False)[:500] if msgs else "ComfyUI 执行错误"
            task["finished_at"] = time.time()
        elif entry.get("outputs"):
            imgs = []
            for out in entry["outputs"].values():
                for img in out.get("images", []):
                    imgs.append({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                 "type": img.get("type", "output")})
            if imgs:
                task["images"] = imgs
                task["status"] = "done"
                task["finished_at"] = time.time()
    else:
        try:
            q = comfy_get("/queue", timeout=10)
            running = [item[1] for item in q.get("queue_running", [])]
            pending = [item[1] for item in q.get("queue_pending", [])]
            if task["prompt_id"] in running:
                task["status"] = "running"
                task["queue_position"] = None
            elif task["prompt_id"] in pending:
                task["status"] = "queued"
                task["queue_position"] = pending.index(task["prompt_id"]) + 1
        except Exception:
            pass

@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["status"] not in ("error",):
        _refresh_status(task)
    return _task_view(task)

@app.get("/tasks/{task_id}/images")
def list_images(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    params = task["params"]
    images = [{"index": i, "url": f"/tasks/{task_id}/images/{i}",
               "width": params["width"], "height": params["height"],
               "filename": img["filename"]}
              for i, img in enumerate(task["images"])]
    return {"status": task["status"], "images": images}

@app.get("/tasks/{task_id}/images/{index}")
def get_image(task_id: str, index: int):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["status"] != "done" or not task["images"]:
        raise HTTPException(409, "任务未完成，无图片可下载")
    if index < 0 or index >= len(task["images"]):
        raise HTTPException(400, f"index 超范围，共 {len(task['images'])} 张")
    img = task["images"][index]
    try:
        data = comfy_get_binary(f"/view?filename={img['filename']}&subfolder={img['subfolder']}&type={img['type']}")
    except Exception as e:
        raise HTTPException(502, f"从 ComfyUI 读取图片失败: {e}")
    return Response(content=data, media_type="image/png",
                    headers={"Content-Disposition": f'inline; filename="{task_id}_{index}.png"'})

@app.get("/status")
def status():
    service = {"status": "ok", "version": VERSION}
    comfyui = {"status": "ok"}
    # GPU 状态
    gpu = {}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        parts = [p.strip() for p in out.split(",")]
        gpu = {"name": parts[0], "memory_used_mb": int(parts[1]), "memory_total_mb": int(parts[2]),
               "utilization_pct": int(parts[3]), "temperature_c": int(parts[4])}
    except Exception:
        gpu = {"error": "nvidia-smi 不可用"}
    # 队列（失败则 ComfyUI 标记异常）
    queue = {"running": 0, "pending": 0}
    try:
        q = comfy_get("/queue", timeout=10)
        queue = {"running": len(q.get("queue_running", [])), "pending": len(q.get("queue_pending", []))}
    except Exception:
        comfyui = {"status": "error"}
    active = [t for t in TASKS.values() if t["status"] in ("submitted", "queued", "running")]
    return {"service": service, "comfyui": comfyui, "gpu": gpu, "queue": queue,
            "tasks": {"active": len(active), "total": len(TASKS)}}
