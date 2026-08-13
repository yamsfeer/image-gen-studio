"""Image Gen Studio Web UI 入口。

运行：
    python webui/app.py           # 默认 http://127.0.0.1:7860
环境变量（可选覆盖）：IMAGE_API_BASE / IMAGE_API_USER / IMAGE_API_PASSWORD
"""
import gradio as gr

from ui import build_app

if __name__ == "__main__":
    demo = build_app()
    demo.queue(default_concurrency_limit=20)
    demo.launch(server_name="127.0.0.1", server_port=7860,
                theme=gr.themes.Soft(), show_error=True)
