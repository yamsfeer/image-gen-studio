"""Image Gen Studio Web UI 入口。

运行：
    python webui/app.py           # 默认 http://127.0.0.1:7860
环境变量（可选覆盖）：API_BASE / API_USER / API_PASSWORD（或旧名 IMAGE_API_*）
"""
import os
import sys

# 把仓库根加入 sys.path，让 webui 复用 client/client.py（API 客户端唯一实现）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr

from ui import build_app

if __name__ == "__main__":
    demo = build_app()
    demo.queue(default_concurrency_limit=20)
    demo.launch(server_name="127.0.0.1", server_port=7860,
                theme=gr.themes.Soft(), show_error=True)
