#!/usr/bin/env python3
"""交叉对比实验：4 模型 × 2 工作流 = 8 张图
模型：sd15 / sdxl / qwen-image / z-image-turbo
工作流：standard（我们默认）vs popular（官方/社区流行参数）
统一提示词 + 统一 seed → 交叉可比。结果存 JSON + 图片到 /tmp/benchmark/
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import ImageClient

SEED = 42
PROMPT = "a cute shiba inu wearing a red beret sitting by a cafe window, warm golden light, cozy atmosphere, photorealistic, highly detailed"
NEG = "blurry, low quality, deformed limbs, watermark, text"

# 矩阵定义：每格 = (steps, cfg, sampler, scheduler, width, height)
MATRIX = {
    "sd15": {
        "label": "SD 1.5",
        "standard": {"steps": 25, "cfg": 7.0, "sampler": "euler", "scheduler": "normal", "width": 512, "height": 512},
        "popular":  {"steps": 20, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras", "width": 512, "height": 512},
    },
    "sdxl": {
        "label": "SDXL 1.0",
        "standard": {"steps": 20, "cfg": 7.0, "sampler": "euler", "scheduler": "normal", "width": 1024, "height": 1024},
        "popular":  {"steps": 20, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras", "width": 1024, "height": 1024},
    },
    "qwen-image": {
        "label": "Qwen-Image (Q3_GGUF)",
        "standard": {"steps": 30, "cfg": 4.0, "sampler": "euler", "scheduler": "karras", "width": 1024, "height": 1024},
        # 网上流行：官方 distill example 的 res_multistep/simple 低步数配置
        "popular":  {"steps": 12, "cfg": 1.0, "sampler": "res_multistep", "scheduler": "simple", "width": 1280, "height": 1280},
    },
    "z-image-turbo": {
        "label": "Z-Image-Turbo (fp8)",
        "standard": {"steps": 8, "cfg": 1.0, "sampler": "dpmpp_2m", "scheduler": "karras", "width": 1024, "height": 1024},
        "popular":  {"steps": 8, "cfg": 3.0, "sampler": "dpmpp_2m", "scheduler": "karras", "width": 1024, "height": 1024},
    },
}

def main():
    os.makedirs("/tmp/benchmark", exist_ok=True)
    c = ImageClient.from_env()  # 连接参数来自 .env / 环境变量（API_BASE / API_USER / API_PASSWORD）
    tasks = []  # {model, workflow, params, task_id}
    for model, m in MATRIX.items():
        for wf in ("standard", "popular"):
            params = m[wf]
            print(f"提交 {model} / {wf}: {params}")
            r = c.generate(model, PROMPT, NEG, params["width"], params["height"],
                           params["steps"], params["cfg"], SEED, 1,
                           sampler=params["sampler"], scheduler=params["scheduler"])
            tasks.append({"model": model, "workflow": wf, "params": params,
                          "task_id": r["task_id"]})
            print(f"  -> {r['task_id']}")
    # 保存任务清单
    with open("/tmp/benchmark/tasks.json", "w") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=1)
    print(f"\n已提交 {len(tasks)} 个任务，轮询等待...")

    # 轮询直到全部完成
    results = []
    pending = list(tasks)
    t0 = time.time()
    while pending:
        time.sleep(5)
        still = []
        for t in pending:
            try:
                st = c.task(t["task_id"])
            except Exception as e:
                print("查询失败", t["task_id"], e); still.append(t); continue
            if st["status"] in ("done", "error"):
                results.append({**t, "status": st["status"],
                                "elapsed": st.get("elapsed_seconds"),
                                "images": st.get("images"),
                                "error": st.get("error")})
                print(f"[{time.time()-t0:.0f}s] {t['model']}/{t['workflow']}: {st['status']} "
                      f"{st.get('elapsed_seconds')}s")
            else:
                still.append(t)
        pending = still
    with open("/tmp/benchmark/results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("\n全部完成，结果在 /tmp/benchmark/results.json")

    # 下载所有图片
    for r in results:
        if r["status"] != "done":
            continue
        out = f"/tmp/benchmark/{r['model']}__{r['workflow']}.png"
        c.download(r["task_id"], out, 0)
        print("下载:", out)

if __name__ == "__main__":
    main()
