#!/usr/bin/env python3
"""生成交叉对比 HTML：读 results.json + 图片 + 视觉评分 → benchmark.html"""
import base64, json, os, subprocess, sys

VISION = "/Users/yams/.agents/skills/deepseek-vision/scripts/vision.js"
MATRIX = {
    "sd15": {"label": "SD 1.5", "desc": "2022 年开源，最老的基础模型"},
    "sdxl": {"label": "SDXL 1.0", "desc": "2023，1024 原生分辨率"},
    "qwen-image": {"label": "Qwen-Image", "desc": "阿里通义千问团队 20B，GGUF Q3 量化"},
    "z-image-turbo": {"label": "Z-Image-Turbo", "desc": "阿里通义万相团队 6B，DMD 蒸馏 8 步"},
}
WF_DESC = {
    "standard": "我们的默认参数",
    "popular": "网上流行/官方推荐参数",
}

def score_image(path):
    """调用 deepseek-vision 给图片打分：画质、主题符合度、细节，返回 (总分, 评语)"""
    prompt = ("请给这张AI生成图片打分（0-10，10最好）："
              "1)画质清晰度 2)主题符合度（画面是否匹配'柴犬戴红色贝雷帽在咖啡馆窗边'）"
              "3)细节质量（毛发/光线/无畸形肢体）。"
              "只返回格式：总分:X.X 简短评语")
    r = subprocess.run(["node", VISION, path, prompt],
                       capture_output=True, text=True, timeout=120)
    out = (r.stdout or "") + (r.stderr or "")
    # 提取总分
    total = None
    for line in out.splitlines():
        import re
        m = re.search(r"总分[:：]\s*(\d+(?:\.\d+)?)", line)
        if m:
            total = float(m.group(1)); break
    return total, out.strip()[-200:]

def main():
    results = json.load(open("/tmp/benchmark/results.json"))
    scores = {}
    for r in results:
        key = f"{r['model']}__{r['workflow']}"
        img = f"/tmp/benchmark/{key}.png"
        if os.path.exists(img):
            total, comment = score_image(img)
            scores[key] = {"score": total, "comment": comment}
            print(f"评分 {key}: {total}")
        else:
            print(f"缺图 {key}")

    # 生成 HTML
    rows = []
    for model, meta in MATRIX.items():
        cells = []
        for wf in ("standard", "popular"):
            key = f"{model}__{wf}"
            img_path = f"/tmp/benchmark/{key}.png"
            b64 = ""
            if os.path.exists(img_path):
                b64 = base64.b64encode(open(img_path, "rb").read()).decode()
            r = next((x for x in results if x["model"] == model and x["workflow"] == wf), {})
            s = scores.get(key, {})
            sc = s.get("score")
            sc_html = f'<span class="score">{sc:.1f}</span>' if sc else '<span class="score">—</span>'
            status = "error" if r.get("status") == "error" else ""
            err = r.get("error") or ""
            cells.append(f"""
            <td>
              <div class="cell-top">{sc_html}
                <span class="meta">{r.get('elapsed_seconds','?')}s</span></div>
              <div class="img-wrap">
                <img src="data:image/png;base64,{b64}" alt="{key}" loading="lazy">
              </div>
              <div class="params">{json.dumps({k:v for k,v in (r.get('params') or {}).items()}, ensure_ascii=False)}</div>
              <div class="wf-name">{WF_DESC[wf]}</div>
              {f'<div class="err">{err[:120]}</div>' if err else ''}
            </td>""")
        rows.append(f"""
        <tr>
          <th class="model-col">
            <div class="model-name">{meta['label']}</div>
            <div class="model-desc">{meta['desc']}</div>
          </th>
          {''.join(cells)}
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>生图模型 × 工作流 交叉对比</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background:#f5f6f8; margin:0; padding:24px; }}
  h1 {{ font-size:20px; color:#1a1a2e; }}
  .sub {{ color:#666; font-size:13px; margin-bottom:16px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  th, td {{ border:1px solid #e3e6ea; padding:10px; vertical-align:top; }}
  .model-col {{ width:140px; background:#fafbfc; text-align:left; }}
  .model-name {{ font-weight:600; font-size:14px; }}
  .model-desc {{ font-size:11px; color:#888; margin-top:4px; }}
  th.wf {{ background:#f0f4ff; font-size:13px; color:#333; }}
  .img-wrap img {{ width:100%; max-width:340px; height:auto; border-radius:6px; display:block; }}
  .cell-top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
  .score {{ background:#2563eb; color:#fff; padding:2px 10px; border-radius:12px; font-size:14px; font-weight:600; }}
  .meta {{ color:#999; font-size:12px; }}
  .params {{ font-size:10px; color:#777; margin-top:6px; font-family:monospace; }}
  .wf-name {{ font-size:11px; color:#2563eb; margin-top:4px; }}
  .err {{ color:#dc2626; font-size:11px; margin-top:4px; }}
  .comment {{ font-size:11px; color:#555; margin-top:6px; max-width:340px; }}
  .note {{ font-size:12px; color:#666; margin:16px 0; line-height:1.6; }}
</style></head><body>
<h1>生图模型 × 工作流 交叉对比</h1>
<div class="note">
统一提示词（英文）：<code>a cute shiba inu wearing a red beret sitting by a cafe window, warm golden light, photorealistic</code><br>
统一 seed：42 ｜ 运行环境：RTX 2080 Ti 11GB ｜ 评分来自视觉模型（0-10，画质+主题符合+细节）
</div>
<table>
  <tr><th class="model-col">模型</th>
      <th class="wf">工作流 A：standard（默认参数）</th>
      <th class="wf">工作流 B：popular（网上流行/官方推荐）</th></tr>
  {''.join(rows)}
</table>
<p class="note">提示：Qwen-Image 的 popular 用官方蒸馏版配置（低步数 res_multistep）；Z-Image-Turbo 的 popular 用官方推荐 cfg=3。</p>
</body></html>"""
    out = "/tmp/benchmark/benchmark.html"
    open(out, "w").write(html)
    print("HTML 已生成:", out)

if __name__ == "__main__":
    main()
