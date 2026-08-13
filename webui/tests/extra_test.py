"""补充测试：空提示词校验 / Z-Image 生成 / 历史回看。

用法：python webui/tests/extra_test.py [--shot-dir /tmp/webui_shots]
"""
import argparse
import os
import time

from playwright.sync_api import sync_playwright

FAILURES = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILURES.append(name)


def select_preset(page, label):
    page.locator("#preset-dropdown input[role='combobox']").click()
    page.wait_for_timeout(400)
    page.locator("[role='option']", has_text=label).first.click()
    page.wait_for_timeout(800)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    ap.add_argument("--shot-dir", default="/tmp/webui_shots")
    args = ap.parse_args()
    os.makedirs(args.shot_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(args.url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_selector("text=Image Gen Studio", timeout=30000)
        page.wait_for_timeout(2500)

        # ── 空提示词校验 ──
        print("\n== 空提示词 ==")
        page.locator("#prompt-box textarea").fill("")
        page.locator("#generate-btn").click()
        page.wait_for_timeout(1500)
        s = page.locator("#status-label").inner_text()
        check("空提示词被拦截", "提示词" in s, s.replace("\n", " ")[:60])

        # ── Z-Image-Turbo 生成（约 40s）──
        print("\n== Z-Image-Turbo · 官方推荐 生成 ==")
        select_preset(page, "Z-Image-Turbo · 官方推荐")
        page.locator("#prompt-box textarea").fill("a cozy cabin in snowy forest")
        page.locator("#generate-btn").click()
        page.wait_for_timeout(1500)
        t0 = time.time()
        final = ""
        while time.time() - t0 < 120:
            page.wait_for_timeout(2000)
            txt = page.locator("#status-label").inner_text()
            if "完成" in txt:
                final = txt
                break
            if "失败" in txt or "❌" in txt:
                final = txt
                break
        print(f"  耗时 {time.time()-t0:.0f}s: {final.replace(chr(10),' ')[:70]}")
        check("Z-Image 生成完成", "完成" in final and "❌" not in final, final[:70])
        if "❌" in final:
            print("  ⛔", final)

        # ── 历史回看（点击历史图库缩略图按钮）──
        print("\n== 历史回看 ==")
        page.wait_for_timeout(800)
        thumbs = page.locator("#history-gallery button.thumbnail-item")
        print("  历史图库缩略图数量:", thumbs.count())
        if thumbs.count():
            thumbs.first.click()  # 真实点击触发 select 事件
            page.wait_for_timeout(1500)
            st = page.locator("#status-label").inner_text()
            imgs = page.locator("#result-gallery img")
            check("点击缩略图后状态显示回看", "回看" in st, st.replace("\n", " ")[:60])
            check("画廊回显历史图片", imgs.count() > 0, f"img count={imgs.count()}")
            page.screenshot(path=os.path.join(args.shot_dir, "04_history_lookup.png"))
        else:
            check("历史图库有可点击缩略图", False, "无缩略图")

        browser.close()
    print(f"\n===== 结果：{len(FAILURES)} 项失败 =====")
    for f in FAILURES:
        print("  ✗", f)
    import sys
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
