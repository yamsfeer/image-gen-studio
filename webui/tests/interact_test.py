"""Playwright 交互测试：预设切换→参数填充→端到端生成→结果/历史/下载。

用法：
    python webui/tests/interact_test.py [--url http://127.0.0.1:7860]
                                        [--no-generate]   # 只测 UI 层，不真实出图
                                        [--shot-dir /tmp/webui_shots]
"""
import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright

FAILURES = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILURES.append(name)


# ---- gradio 6 组件取值辅助 ----
# range-input 顺序：0=steps 1=cfg 2=width 3=height
# role=combobox 顺序：0=预设 1=sampler 2=scheduler（Accordion 展开后）
# input[type=number] 顺序：0=steps 1=cfg 2=seed 3=width 4=height
def slider_val(page, idx):
    return float(page.locator("[data-testid='range-input']").nth(idx).input_value())


def combo_val(page, idx):
    return page.locator("[role=combobox]").nth(idx).input_value()


def num_val(page, idx):
    return page.locator("input[type='number']").nth(idx).input_value()


def select_preset(page, label):
    """打开预设下拉并选中指定 label。"""
    page.locator("#preset-dropdown input[role='combobox']").click()
    page.wait_for_timeout(400)
    page.locator(f"[role='option']", has_text=label).first.click()
    page.wait_for_timeout(800)  # 等 change 事件回流


def open_advanced(page):
    page.locator("button", has_text="高级参数").click()
    page.wait_for_timeout(600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--shot-dir", default="/tmp/webui_shots")
    args = ap.parse_args()
    os.makedirs(args.shot_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(args.url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_selector("text=Image Gen Studio", timeout=30000)
        page.wait_for_timeout(2500)

        # ── GPU 状态条（stats_timer 每 10s 更新一次）──
        print("\n== GPU 状态条 ==")
        for _ in range(18):
            txt = page.locator("#gpu-status").inner_text()
            if "加载中" not in txt:
                break
            page.wait_for_timeout(1000)
        check("GPU 状态已从占位符刷新", "加载中" not in txt, txt[:90])

        # ── 阶段 A：预设切换 → 参数自动填充 ──
        print("\n== 阶段 A：预设 → 参数填充 ==")
        open_advanced(page)

        select_preset(page, "SD 1.5 · 标准")
        print("  SD 1.5 · 标准 →", slider_val(page, 0), "步,",
              combo_val(page, 1), "/", combo_val(page, 2),
              "seed", num_val(page, 2))
        check("sd15-standard steps=25", slider_val(page, 0) == 25)
        check("sd15-standard cfg=7", slider_val(page, 1) == 7.0)
        check("sd15-standard width=512", slider_val(page, 2) == 512)
        check("sd15-standard height=512", slider_val(page, 3) == 512)
        check("sd15-standard sampler=euler", combo_val(page, 1) == "euler")
        check("sd15-standard scheduler=normal", combo_val(page, 2) == "normal")
        check("sd15-standard seed 复位 -1", num_val(page, 2) == "-1")

        # qwen-standard（高质量）现为官方蒸馏配置
        select_preset(page, "Qwen-Image · 高质量")
        print("  Qwen-Image · 高质量 →", slider_val(page, 0), "步,",
              combo_val(page, 1), "/", combo_val(page, 2))
        check("qwen-standard steps=12", slider_val(page, 0) == 12)
        check("qwen-standard cfg=1", slider_val(page, 1) == 1.0)
        check("qwen-standard width=1280", slider_val(page, 2) == 1280)
        check("qwen-standard sampler=res_multistep", combo_val(page, 1) == "res_multistep")
        check("qwen-standard scheduler=simple", combo_val(page, 2) == "simple")

        select_preset(page, "Qwen-Image · 官方蒸馏配置")
        print("  Qwen-Image · 官方蒸馏配置 →", slider_val(page, 0), "步,",
              combo_val(page, 1), "/", combo_val(page, 2))
        check("qwen-popular steps=20", slider_val(page, 0) == 20)
        check("qwen-popular cfg=3.5", slider_val(page, 1) == 3.5)
        check("qwen-popular width=1280", slider_val(page, 2) == 1280)
        check("qwen-popular sampler=dpmpp_2m", combo_val(page, 1) == "dpmpp_2m")
        check("qwen-popular scheduler=karras", combo_val(page, 2) == "karras")

        # ── 阶段 B：生成流程（默认关，--no-generate 跳过）──
        if args.no_generate:
            browser.close()
            _summary()
            return

        print("\n== 阶段 B：端到端生成（SD 1.5 · 标准，最快）==")
        select_preset(page, "SD 1.5 · 标准")
        page.locator("#prompt-box textarea").fill("a red apple on a wooden table")
        page.screenshot(path=os.path.join(args.shot_dir, "02_before_generate.png"))

        t0 = time.time()
        page.locator("#generate-btn").click()
        page.wait_for_timeout(1500)
        status0 = page.locator("#status-label").inner_text()
        print(f"  提交后状态: {status0[:60]}")
        check("点击生成后状态变为'已提交/排队'",
              ("已提交" in status0 or "排队" in status0 or "生成中" in status0), status0[:50])

        # 轮询直到完成 / 失败 / 超时
        final = ""
        sampled = []
        while time.time() - t0 < 150:
            page.wait_for_timeout(1000)
            txt = page.locator("#status-label").inner_text()
            if time.time() - t0 < 12:
                sampled.append(txt[:40])
            if "完成" in txt or "失败" in txt or "❌" in txt:
                final = txt
                break
        print(f"  耗时 {time.time()-t0:.0f}s，期间状态: {sampled}")
        check("任务完成", "完成" in final and "❌" not in final, final[:80])
        if "❌" in final:
            print("  生成失败:", final)

        if "完成" in final:
            page.screenshot(path=os.path.join(args.shot_dir, "03_done.png"))
            # 画廊有图
            imgs = page.locator("#result-gallery img")
            check("结果画廊出现图片", imgs.count() > 0, f"img count={imgs.count()}")
            # 历史表格出现含提示词的数据单元格
            cell = page.locator("#history-table .cell-wrap", has_text="red apple").first
            check("历史表格新增数据行", cell.count() > 0,
                  page.locator("#history-table").inner_text().replace("\n", " | ")[:120])
            # 下载按钮可用并触发下载
            try:
                with page.expect_download(timeout=8000) as dl:
                    page.locator("#download-btn").click()
                d = dl.value
                check("下载按钮可下载文件", True, d.suggested_filename)
            except Exception as e:
                check("下载按钮可下载文件", False, str(e)[:80])

        browser.close()
    _summary()


def _summary():
    print(f"\n===== 结果：{len(FAILURES)} 项失败 =====")
    for f in FAILURES:
        print("  ✗", f)
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
