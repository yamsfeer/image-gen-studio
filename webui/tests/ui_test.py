"""Playwright UI 冒烟测试：加载页面 → 截图 → 探测关键元素结构。

用法：
    python webui/tests/ui_test.py [--url http://127.0.0.1:7860] [--shot-dir /tmp/webui_shots]
"""
import argparse
import os

from playwright.sync_api import sync_playwright


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
        # 等 gradio Svelte 前端挂载出标题
        page.wait_for_selector("text=Image Gen Studio", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(args.shot_dir, "01_loaded.png"), full_page=True)
        print("title:", page.title())

        # 探测关键文本
        body = page.locator("body").inner_text()
        for kw in ["Image Gen Studio", "预设", "提示词", "生成", "下载", "GPU", "历史"]:
            print(f"  contains {kw!r}:", kw in body)

        # 探测常见 gradio 组件 role 结构
        combos = page.locator("role=combobox")
        print("combobox count:", combos.count())
        for i in range(combos.count()):
            txt = combos.nth(i).inner_text()[:60].replace("\n", " | ")
            print(f"  combobox[{i}]: {txt}")

        buttons = page.locator("button")
        print("button count:", buttons.count())
        for i in range(buttons.count()):
            t = buttons.nth(i).inner_text()
            if t.strip():
                print(f"  button[{i}]: {t.strip()[:40]!r}")

        browser.close()


if __name__ == "__main__":
    main()
