"""生图服务：包装 ComfyUI 后端的 HTTP API
- POST /generate   提交生图任务（指定模型/提示词/参数），立即返回 task_id
- GET  /task/{id}  轮询任务状态（排队/运行/完成/出错 + 实时进度）
- GET  /stats      显卡状态 + 队列情况
- GET  /image/{task_id}  下载生成图片
- GET  /models     列出可用模型
"""
import asyncio, json, os, subprocess, time, uuid
from typing import Optional, List

import requests
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from workflows import MODELS

COMFY = "http://127.0.0.1:8188"
CLIENT_ID = "image-service-" + uuid.uuid4().hex[:8]  # WebSocket 进度监听用同一个 client_id

app = FastAPI(title="Image Service", version="1.0.0")

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
class GenerateRequest(BaseModel):
    model: str = "qwen-image"
    prompt: str = Field(..., min_length=1)
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg: float = 4.0
    seed: int = Field(default_factory=lambda: int(time.time()))
    batch_size: int = 1
    sampler: Optional[str] = None   # 覆盖模型默认采样器
    scheduler: Optional[str] = None # 覆盖模型默认调度器

# ---------------- 接口 ----------------
@app.get("/")
def root():
    return {"service": "image-service", "models": list(MODELS), "docs": "/docs"}

@app.get("/models")
def list_models():
    return [{"id": k, **{kk: v for kk, v in m.items() if kk != "builder"}} for k, m in MODELS.items()]

@app.post("/generate")
def generate(req: GenerateRequest):
    if req.model not in MODELS:
        raise HTTPException(400, f"未知模型: {req.model}，可用: {list(MODELS)}")
    if not req.prompt.strip():
        raise HTTPException(400, "prompt 不能为空")
    if not (256 <= req.width <= 2048 and 256 <= req.height <= 2048):
        raise HTTPException(400, "宽高需在 256-2048 之间")
    if req.width % 64 or req.height % 64:
        raise HTTPException(400, "宽高需为 64 的倍数")
    if not (1 <= req.steps <= 100):
        raise HTTPException(400, "steps 需在 1-100")
    if not (1.0 <= req.cfg <= 20.0):
        raise HTTPException(400, "cfg 需在 1-20")
    if not (1 <= req.batch_size <= 4):
        raise HTTPException(400, "batch_size 需在 1-4")

    task_id = uuid.uuid4().hex
    task = {
        "task_id": task_id,
        "model": req.model,
        "prompt": req.prompt,
        "params": {"width": req.width, "height": req.height, "steps": req.steps,
                   "cfg": req.cfg, "seed": req.seed, "batch_size": req.batch_size},
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
        defaults = MODELS[req.model]["defaults"]
        sampler = req.sampler or defaults.get("sampler", "euler")
        scheduler = req.scheduler or defaults.get("scheduler", "normal")
        workflow = MODELS[req.model]["builder"](
            req.prompt, req.negative_prompt, req.width, req.height,
            req.steps, req.cfg, req.seed, req.batch_size, sampler, scheduler)
        r = comfy_post("/prompt", {"prompt": workflow, "client_id": CLIENT_ID})
        task["prompt_id"] = r["prompt_id"]
        task["status"] = "queued"
    except Exception as e:
        task["status"] = "error"
        task["error"] = f"提交到 ComfyUI 失败: {e}"

    return {"task_id": task_id, "status": task["status"], "prompt_id": task["prompt_id"]}

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

@app.get("/task/{task_id}")
def get_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["status"] not in ("error",):
        _refresh_status(task)
    elapsed = (task.get("finished_at") or time.time()) - task["created_at"]
    return {
        "task_id": task_id,
        "model": task["model"],
        "status": task["status"],
        "queue_position": task["queue_position"],
        "progress": task["progress"],
        "images": [f"/image/{task_id}?index={i}" for i in range(len(task["images"]))],
        "error": task["error"],
        "elapsed_seconds": round(elapsed, 1),
    }

@app.get("/image/{task_id}")
def get_image(task_id: str, index: int = 0):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["status"] != "done" or not task["images"]:
        raise HTTPException(409, "任务未完成，无图片可下载")
    if index >= len(task["images"]):
        raise HTTPException(400, f"index 超范围，共 {len(task['images'])} 张")
    img = task["images"][index]
    try:
        data = comfy_get_binary(f"/view?filename={img['filename']}&subfolder={img['subfolder']}&type={img['type']}")
    except Exception as e:
        raise HTTPException(502, f"从 ComfyUI 读取图片失败: {e}")
    return Response(content=data, media_type="image/png",
                    headers={"Content-Disposition": f'inline; filename="{task_id}_{index}.png"'})

@app.get("/stats")
def stats():
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
    # 队列
    queue = {"running": 0, "pending": 0}
    try:
        q = comfy_get("/queue", timeout=10)
        queue = {"running": len(q.get("queue_running", [])), "pending": len(q.get("queue_pending", []))}
    except Exception:
        pass
    active = [t for t in TASKS.values() if t["status"] in ("submitted", "queued", "running")]
    return {"gpu": gpu, "queue": queue, "active_tasks": len(active), "total_tasks": len(TASKS)}
