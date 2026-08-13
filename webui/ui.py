"""Gradio 界面布局与事件绑定。布局对应 PLAN.md 第 5 节：

    顶部状态条(F6) / 左列：预设(F1)+高级参数(F3)+历史(F7)
    右列：提示词(F2)+生成(F4)+状态+结果画廊(F5)
"""
import gradio as gr

import handlers
from config import POLL_INTERVAL, SAMPLERS, SCHEDULERS, STATS_INTERVAL
from presets import dropdown_choices, get_presets

# 历史表格列：(标题, 数据类型)
HISTORY_COLUMNS = [
    ("时间", "str"), ("预设", "str"), ("模型", "str"), ("提示词", "str"),
    ("步数", "number"), ("seed", "number"), ("耗时", "str"),
]


def build_app():
    first = get_presets()[0]
    with gr.Blocks(title="Image Gen Studio") as demo:
        # ── 顶部：标题 + GPU 状态条 ──
        with gr.Row():
            gr.Markdown("# 🎨 Image Gen Studio")
            gpu_html = gr.HTML('<span style="color:#888">GPU 状态加载中…</span>',
                               elem_id="gpu-status")

        with gr.Row():
            # ══ 左列：预设 + 高级参数 + 历史 ══
            with gr.Column(scale=5):
                gr.Markdown("### ① 预设模板")
                preset_dd = gr.Dropdown(
                    choices=dropdown_choices(),
                    label="选择预设",
                    value=first["id"],
                    elem_id="preset-dropdown",
                )
                preset_desc = gr.Markdown(
                    f"**{first['label']}**  ·  {first['desc']}", elem_id="preset-desc")

                with gr.Accordion("⚙️ 高级参数（默认跟随预设，可覆盖）", open=False):
                    with gr.Row():
                        steps_sl = gr.Slider(1, 100, step=1, value=30, label="采样步数 steps",
                                             elem_id="param-steps")
                        cfg_sl = gr.Slider(1.0, 20.0, step=0.5, value=4.0, label="CFG",
                                           elem_id="param-cfg")
                    with gr.Row():
                        seed_num = gr.Number(value=-1, label="seed（-1 随机）",
                                             elem_id="param-seed")
                        sampler_dd = gr.Dropdown(SAMPLERS, value="euler", label="sampler",
                                                 elem_id="param-sampler")
                    with gr.Row():
                        width_sl = gr.Slider(256, 2048, step=64, value=1024, label="宽度",
                                             elem_id="param-width")
                        height_sl = gr.Slider(256, 2048, step=64, value=1024, label="高度",
                                              elem_id="param-height")
                    scheduler_dd = gr.Dropdown(SCHEDULERS, value="karras", label="scheduler",
                                               elem_id="param-scheduler")

                gr.Markdown("### ⑦ 会话历史（点击下方缩略图回看）")
                history_gallery = gr.Gallery(
                    label="历史图库", columns=4, height=200,
                    format="png", allow_preview=False,
                    elem_id="history-gallery")
                history_df = gr.Dataframe(
                    headers=[c for c, _ in HISTORY_COLUMNS],
                    datatype=[t for _, t in HISTORY_COLUMNS],
                    interactive=False,
                    wrap=True,
                    label="参数明细",
                    max_height=200,
                    elem_id="history-table",
                )

            # ══ 右列：提示词 + 生成 + 结果 ══
            with gr.Column(scale=6):
                gr.Markdown("### ③ 提示词")
                prompt_tb = gr.Textbox(
                    lines=4,
                    placeholder="描述你想生成的画面…",
                    label="主提示词（必填）",
                    elem_id="prompt-box",
                )
                negative_tb = gr.Textbox(
                    lines=2,
                    placeholder="负面提示词（可选；Z-Image 模型会自动忽略）",
                    label="负面提示词",
                    elem_id="negative-box",
                )

                with gr.Row():
                    gen_btn = gr.Button("🚀 生成", variant="primary", elem_id="generate-btn")
                    download_btn = gr.DownloadButton("⬇ 下载图片", elem_id="download-btn")

                status_lb = gr.Label("就绪", label="状态", elem_id="status-label")

                gallery = gr.Gallery(
                    label="结果", columns=2, height=360,
                    object_fit="contain", format="png", elem_id="result-gallery")

        # ── 会话状态 ──
        task_state = gr.State(None)
        history_state = gr.State([])

        # ── 定时器：任务轮询(默认停) + GPU 状态(一直跑) ──
        task_timer = gr.Timer(POLL_INTERVAL, active=False)
        stats_timer = gr.Timer(STATS_INTERVAL, active=True)

        # ── 事件绑定 ──
        preset_dd.change(
            handlers.on_preset_change, [preset_dd],
            [preset_desc, steps_sl, cfg_sl, seed_num, width_sl, height_sl,
             sampler_dd, scheduler_dd],
        )

        gen_btn.click(
            handlers.on_generate,
            [prompt_tb, negative_tb, preset_dd, steps_sl, cfg_sl, seed_num,
             width_sl, height_sl, sampler_dd, scheduler_dd],
            [status_lb, task_state, task_timer],
        )

        task_timer.tick(
            handlers.poll_task, [task_state, history_state],
            [status_lb, gallery, history_state, download_btn, task_timer,
             history_df, history_gallery],
        )

        stats_timer.tick(handlers.fetch_stats, None, [gpu_html])

        history_gallery.select(
            handlers.on_history_gallery_select, [history_state],
            [gallery, status_lb, download_btn],
        )

    return demo
