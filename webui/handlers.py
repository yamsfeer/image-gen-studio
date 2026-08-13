"""Gradio 事件处理函数：预设填充、生成提交、任务轮询、GPU 状态、历史回看。

所有函数签名与 ui.py 里的事件绑定一一对应；返回值按 outputs 顺序排列，
其中返回 None 表示"该组件不更新"。
"""
import io
import os
import time
from datetime import datetime

import gradio as gr
from PIL import Image

from api_client import ApiError, ImageClient
from config import API_BASE, API_PASSWORD, API_USER, DOWNLOAD_DIR
from presets import find_preset, get_presets

_client = ImageClient(API_BASE, API_USER, API_PASSWORD)

SEED_RANDOM = -1  # UI 中 -1 表示随机种子


# ---------- 小工具 ----------
def _format_elapsed(seconds) -> str:
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "-"
    if s < 60:
        return f"{s} 秒"
    return f"{s // 60} 分 {s % 60} 秒"


def _save_image(task_id: str, img: Image.Image) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    path = os.path.join(DOWNLOAD_DIR, f"img_{task_id}.png")
    img.save(path, format="PNG")
    return path


# ---------- ① 预设选择 → 自动填充参数 ----------
def on_preset_change(preset_id):
    p = find_preset(preset_id)
    if not p:
        return "**未找到预设**", 30, 4.0, SEED_RANDOM, 1024, 1024, "euler", "karras"
    pr = p["params"]
    desc = f"**{p['label']}**  ·  {p['desc']}"
    return (desc, pr["steps"], pr["cfg"], SEED_RANDOM, pr["width"], pr["height"],
            pr["sampler"], pr["scheduler"])


# ---------- ④ 生成提交 ----------
def on_generate(prompt, negative, preset_id, steps, cfg, seed,
                width, height, sampler, scheduler):
    prompt = (prompt or "").strip()
    if not prompt:
        return "⚠️ 请先输入主提示词", None, gr.Timer(active=False)

    preset = find_preset(preset_id) or get_presets()[0]
    if seed in (None, "", -1, "-1"):
        seed = int(time.time())  # 随机种子：用时间戳，落进历史便于回看复现

    try:
        r = _client.generate(
            preset["model"], prompt, negative or "",
            width=width, height=height, steps=steps, cfg=cfg,
            seed=seed, sampler=sampler or None, scheduler=scheduler or None)
    except ApiError as e:
        return f"❌ 提交失败：{e}", None, gr.Timer(active=False)

    # task_state 里带上展示所需的元信息，轮询完成时写进历史
    meta = {"task_id": r["task_id"], "preset": preset["label"],
            "model": preset["model"], "steps": int(steps),
            "seed": int(seed), "prompt": prompt[:40]}
    return f"✅ 已提交（{preset['label']}）· 排队中 …", meta, gr.Timer(active=True)


# ---------- ⑤ 任务轮询（每 3s） ----------
def poll_task(task_meta, history):
    # 返回 7 个值：状态 / 画廊 / 历史state / 下载路径 / timer / 历史表格 / 历史图库
    if not task_meta:
        return "就绪", None, None, None, gr.Timer(active=False), None, None

    try:
        st = _client.task(task_meta["task_id"])
    except ApiError as e:
        return (f"❌ 查询失败：{e}", None, None, None,
                gr.Timer(active=False), None, None)

    status = st.get("status")
    print(f"[poll] task={task_meta['task_id'][:8]} status={status} "
          f"prog={st.get('progress')} el={st.get('elapsed_seconds')}", flush=True)

    if status in ("submitted", "queued"):
        pos = st.get("queue_position")
        pos_txt = f"，排在 #{pos}" if pos else ""
        return f"⏳ 排队中{pos_txt} …", None, None, None, None, None, None

    if status == "running":
        p = st.get("progress") or {}
        cur, mx = p.get("value"), p.get("max")
        prog = f"{cur}/{mx}" if cur is not None else "进行中"
        return (f"🖌 生成中 {prog} · 耗时 {_format_elapsed(st.get('elapsed_seconds'))}",
                None, None, None, None, None, None)

    if status == "done":
        try:
            data = _client.image_bytes(task_meta["task_id"])
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except ApiError as e:
            return (f"❌ 图片下载失败：{e}", None, None, None,
                    gr.Timer(active=False), None, None)
        path = _save_image(task_meta["task_id"], img)
        elapsed = _format_elapsed(st.get("elapsed_seconds"))
        rec = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "preset": task_meta.get("preset", "-"),
            "model": task_meta.get("model", "-"),
            "prompt": task_meta.get("prompt", "-"),
            "steps": task_meta.get("steps", "-"),
            "seed": task_meta.get("seed", "-"),
            "elapsed": elapsed,
            "filepath": path,
            "task_id": task_meta["task_id"],
        }
        new_history = (history or []) + [rec]
        # gradio 6 Gallery 的 value 必须是列表；历史表格/图库一并输出
        return (f"✅ 完成！耗时 {elapsed} · 已加入会话历史",
                [img], new_history, path, gr.Timer(active=False),
                _history_rows(new_history), _history_gallery(new_history))

    if status == "error":
        return (f"❌ 生成失败：{st.get('error')}", None, None, None,
                gr.Timer(active=False), None, None)

    return f"状态：{status}", None, None, None, None, None, None


def _history_rows(history):
    """历史 state → Dataframe 二维数组（与 HISTORY_COLUMNS 对齐）。"""
    return [
        [r.get("time", ""), r.get("preset", ""), r.get("model", ""),
         r.get("prompt", ""), r.get("steps", ""), r.get("seed", ""),
         r.get("elapsed", "")]
        for r in history
    ]


def _history_gallery(history):
    """历史 state → 历史图库 Gallery 列表 [(PIL, caption), ...]。

    图片文件保存在本地 DOWNLOAD_DIR，逐张打开。历史很短，v1 够用。
    """
    items = []
    for r in history:
        try:
            img = Image.open(r["filepath"]).convert("RGB")
        except Exception:
            continue
        caption = f"{r.get('time', '')} · {r.get('preset', '')} · {r.get('steps', '')}步"
        items.append((img, caption))
    return items


# ---------- ⑦ 历史回看（点击历史图库缩略图） ----------
def on_history_gallery_select(evt: gr.SelectData, history):
    print(f"[gallery-select] index={evt.index!r}", flush=True)
    history = history or []
    idx = evt.index
    if not isinstance(idx, int) or not (0 <= idx < len(history)):
        return None, "无法定位该记录", None
    rec = history[idx]
    try:
        img = Image.open(rec["filepath"]).convert("RGB")
    except Exception:
        return None, f"图片文件丢失：{rec['filepath']}", None
    txt = (f"🔍 回看 {rec['time']} · {rec['preset']} · {rec['model']} · "
           f"{rec['steps']} 步 · seed {rec['seed']} · 耗时 {rec['elapsed']}")
    return [img], txt, rec["filepath"]


# ---------- ⑦ 历史回看 ----------
def on_history_select(evt: gr.SelectData, history):
    print(f"[select] index={evt.index!r}", flush=True)
    history = history or []
    if not history:
        return None, "暂无历史记录", None
    idx = evt.index
    row = idx[0] if isinstance(idx, (tuple, list)) else idx
    if not isinstance(row, int) or not (0 <= row < len(history)):
        return None, "无法定位该记录", None
    rec = history[row]
    try:
        img = Image.open(rec["filepath"]).convert("RGB")
    except Exception:
        return None, f"图片文件丢失：{rec['filepath']}", None
    txt = (f"🔍 回看 {rec['time']} · {rec['preset']} · {rec['model']} · "
           f"{rec['steps']} 步 · seed {rec['seed']} · 耗时 {rec['elapsed']}")
    return [img], txt, rec["filepath"]


# ---------- ⑥ GPU 状态条（每 10s） ----------
def fetch_stats():
    try:
        st = _client.stats()
    except ApiError as e:
        return _stats_html(f"GPU 离线 · {e}", muted=True)
    gpu = st.get("gpu") or {}
    q = st.get("queue") or {}
    mem_used = gpu.get("memory_used_mb", 0)
    mem_total = gpu.get("memory_total_mb", 0)
    util = gpu.get("utilization_pct", 0)
    temp = gpu.get("temperature_c")
    name = (gpu.get("name") or "GPU").replace("NVIDIA GeForce ", "")[:32]
    color = "#e5484d" if util > 90 else ("#f5a623" if util > 50 else "#30a46c")
    temp_txt = f" · {temp}°C" if temp is not None else ""
    txt = (f"🎮 {name} · 显存 {mem_used:.0f}/{mem_total:.0f} MB · "
           f"利用率 <b>{util}%</b>{temp_txt} · "
           f"队列 {q.get('running', 0)} 跑/{q.get('pending', 0)} 等")
    return _stats_html(txt, color=color)


def _stats_html(text: str, color=None, muted=False) -> str:
    style = "#888" if muted else color or "#ddd"
    return f'<span style="color:{style};font-size:14px">{text}</span>'
