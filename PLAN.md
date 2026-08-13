# PLAN：Image Gen Studio Web UI

> 目标：给后端生图服务做一个 Web 界面——**预设选择 → 填提示词 → 点运行 → 看结果**。
> 本计划写给执行 agent，任务拆解、技术选型、页面设计都已定，按序实现即可。

## 1. 背景与目标

后端已完成（见 docs/server-status.md、docs/api.md）：AutoDL 服务器上跑着
`nginx(Basic Auth) → FastAPI:8190 → ComfyUI:8188`，4 个模型、每模型 2 种工作流参数（standard/popular）。

**要做的**：一个 Web UI，让用户不用命令行，像用"预设模板"一样生图：

```
用户选择预设（如 "Qwen-Image · 高质量"）→ 填提示词 → 点【生成】
  → 前端调 POST /generate → 轮询 /task/{id} 显示进度 → 完成显示图片 → 可下载
```

## 2. 功能需求（v1 范围）

| # | 功能 | 说明 |
|---|---|---|
| F1 | 预设选择 | 8 个预设卡片（4 模型 × 2 工作流），选中显示参数详情 |
| F2 | 提示词输入 | 主提示词（必填）+ 负面提示词（可选，z-image 模型提示会忽略） |
| F3 | 高级参数 | 折叠面板：steps / cfg / seed / 宽高 / sampler / scheduler，默认跟随预设，可覆盖 |
| F4 | 生成与进度 | 点生成 → 调 API → 实时显示状态（排队位置/采样进度 x/y/耗时） |
| F5 | 结果展示 | 完成显示图片 + 该图参数 + 耗时 + 下载按钮；失败显示错误原因 |
| F6 | GPU 状态 | 页面一角显示 /stats（显存/利用率/温度/队列长度） |
| F7 | 历史记录 | 本次会话内生成的历史（图片+参数），可回看下载（v1 内存态即可） |

非目标（v2+）：多图批量、图生图/ControlNet、账号系统、持久化历史、视频生成。

## 3. 技术选型（重要：先读这一段）

**为什么不用 Open WebUI**：Open WebUI 是 **LLM 聊天界面**（对话流式渲染、模型路由、RAG），
后端对接 Ollama / OpenAI 兼容 API。本项目的交互是"表单驱动 + 结果画廊"，不是对话流；
Open WebUI 的 Pipelines 机制能挂工具，但改造出"预设工作流面板"成本高且不自然。**不采用。**

**推荐方案（两级）**：

- **v1 快速交付：Gradio**（Python 单文件，最快跑通）
  - 理由：与现有后端同语言（Python），`gr.Blocks` 直接搭"预设下拉/卡片 + 提示词框 + 参数滑块 + 按钮 + 图库"；
    内置 `.queue()` 排队；本地 `python app.py` 即可跑，无需 node 构建。
  - 缺点：界面观感偏"工具"，不够精致。
- **v2 产品化：Vue3 + Vite + Element Plus**（SPA）
  - 前后端分离，静态托管；更精致的卡片式 UI、暗色主题；后端 API 不变。
  - 需要 node 环境构建，工作量约 v1 的 3-4 倍。

**执行建议**：先做 v1（Gradio）保证当天可用，若时间允许再升级 v2。两份实现共用同一份预设配置 JSON 和后端 API。

## 4. 预设配置（数据结构，与后端对齐）

新建 `presets.json`（前端共享配置，字段与 /generate 请求体一一对应）：

```json
{
  "presets": [
    {"id": "qwen-standard", "label": "Qwen-Image · 高质量", "model": "qwen-image",
     "workflow": "standard",
     "params": {"steps": 30, "cfg": 4.0, "sampler": "euler", "scheduler": "karras",
                "width": 1024, "height": 1024},
     "desc": "阿里通义千问 20B（GGUF Q3），中文强，30 步约 8.5 分钟"},
    {"id": "qwen-popular", "label": "Qwen-Image · 官方蒸馏配置", "model": "qwen-image",
     "workflow": "popular",
     "params": {"steps": 12, "cfg": 1.0, "sampler": "res_multistep", "scheduler": "simple",
                "width": 1280, "height": 1280},
     "desc": "官方 example 的低步数配置，快很多"},
    {"id": "sdxl-standard", "label": "SDXL · 标准", "model": "sdxl", "workflow": "standard",
     "params": {"steps": 20, "cfg": 7.0, "sampler": "euler", "scheduler": "normal",
                "width": 1024, "height": 1024}, "desc": "英文提示词效果最佳，约 16 秒"},
    {"id": "sdxl-popular", "label": "SDXL · 流行配置", "model": "sdxl", "workflow": "popular",
     "params": {"steps": 20, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
                "width": 1024, "height": 1024}, "desc": "dpmpp_2m + karras，社区常用"},
    {"id": "zimage-standard", "label": "Z-Image-Turbo · 极速", "model": "z-image-turbo",
     "workflow": "standard",
     "params": {"steps": 8, "cfg": 1.0, "sampler": "dpmpp_2m", "scheduler": "karras",
                "width": 1024, "height": 1024}, "desc": "阿里通义万相 6B，8 步约 40 秒"},
    {"id": "zimage-popular", "label": "Z-Image-Turbo · 官方推荐", "model": "z-image-turbo",
     "workflow": "popular",
     "params": {"steps": 8, "cfg": 3.0, "sampler": "dpmpp_2m", "scheduler": "karras",
                "width": 1024, "height": 1024}, "desc": "官方推荐 cfg=3"},
    {"id": "sd15-standard", "label": "SD 1.5 · 标准", "model": "sd15", "workflow": "standard",
     "params": {"steps": 25, "cfg": 7.0, "sampler": "euler", "scheduler": "normal",
                "width": 512, "height": 512}, "desc": "最老模型，仅基准对比"},
    {"id": "sd15-popular", "label": "SD 1.5 · 流行配置", "model": "sd15", "workflow": "popular",
     "params": {"steps": 20, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
                "width": 512, "height": 512}, "desc": "dpmpp_2m + karras"}
  ]
}
```

> 提示：模型选择后负面提示词默认留空（z-image-turbo 的 DMD 蒸馏不吃负向）。

## 5. 页面设计（Gradio v1 布局）

```
┌────────────────────────────────────────────────────────────┐
│  🎨 Image Gen Studio           [GPU: 10229MB/11264MB 97%]  │  ← F6 状态条
├──────────────────────────────┬─────────────────────────────┤
│  ① 预设选择（gr.Dropdown 或  │  ③ 提示词（gr.Textbox 大）  │
│     卡片按钮组，8 个）        │     负面提示词（小，可选）   │
│  ② 高级参数（gr.Accordion 折叠│                            │
│     steps/cfg/seed/宽高/      │  ④ 【生成】按钮            │
│     sampler/scheduler）       │  ⑤ 状态/进度（gr.Label）   │
│                              │  ⑥ 结果画廊（gr.Gallery）  │
└──────────────────────────────┴─────────────────────────────┘
```

交互逻辑：
1. 选预设 → 自动填充高级参数（用户可改）
2. 点生成 → 调 `POST /generate` → 存 task_id → 起轮询（每 3-5s 调 `/task/{id}`）
3. 轮询期间更新状态文本：排队（显示 queue_position）/ 运行（progress x/y）/ 耗时
4. done → 调 `/image/{id}` 下载图片 → 显示在画廊 + 记录历史（参数、耗时）
5. error → 红字显示 error 字段
6. GPU 状态条：每 10s 调一次 `/stats`

## 6. 实现任务拆解

| 任务 | 内容 | 产出 |
|---|---|---|
| T1 | 初始化 v1 项目（`webui/` 目录），装 gradio | 可运行空页面 |
| T2 | 写 `presets.json`（上节内容） | 配置就绪 |
| T3 | API 对接层：封装 generate/task/image/stats 四个调用（Basic Auth + 隧道 base URL，参考 client/client.py 逻辑） | `api_client.py` |
| T4 | 核心界面：预设选择 + 提示词 + 高级参数 + 生成按钮 + 结果画廊 | F1-F5 可用 |
| T5 | 进度轮询 + 错误处理 + GPU 状态条 + 会话历史 | F6-F7 |
| T6 | 联调：本机建隧道 → 跑通"选预设→生成→出图"全流程 | 验收 |
| T7（可选 v2）| Vue3 + Vite SPA 产品化 | 精致版 UI |

## 7. 联调与部署

- 前置条件：本机 SSH 隧道已建（连接信息从 `.env` 读，见 README「配置」节）
- 开发：`python webui/app.py` → 浏览器打开 Gradio 默认地址（127.0.0.1:7860）
- Base URL 配置：`webui/config.py` 读 `.env`（`API_BASE` / `API_USER` / `API_PASSWORD`，也支持环境变量覆盖）
- 部署选项：本机运行（最简，推荐 v1）；或部署到服务器由 nginx 反代（v2 再考虑）

## 8. 验收标准

- [x] 8 个预设均可选，选中后参数面板自动填充（Playwright 断言通过）
- [~] 修改提示词 + 点生成，能出图（sd15 / z-image-turbo 已实跑通过；sdxl / qwen-image 待用户实测）
- [x] 生成期间能看到排队位置/进度/耗时，完成后显示图片并可下载
- [x] 错误场景（空提示词 / 后端不可达 / 任务失败）有明确提示
- [x] GPU 状态条实时更新（每 10s 刷新 /stats）
- [x] 会话内历史可回看（参数明细表 + 图片缩略图点击回看）

## 9b. 实现状态（2026-08-13）

v1（Gradio 6）已实现并通过 Playwright 自动化测试（`webui/tests/` 三个脚本全绿）：

- 启动：`python3 webui/app.py` → http://127.0.0.1:7860
- 预设参数已被用户实测校准（见 `webui/presets.json`，qwen/z-image 的官方蒸馏配置已更新）
- 已知 gradio 6 坑（详见 `webui/README.md`）：Gallery value 需列表、Dataframe 动态更新后点击 select 不可用（历史回看改用图库缩略图）、事件数据需 `gr.SelectData` 注解
- v2（Vue3 SPA 产品化）未做，属可选后续

## 9. 可复用资产（本项目已有）

- `client/client.py` —— API 客户端（直接 import 或用它的逻辑）
- `client/benchmark.py` —— 矩阵参数参考（MATRIX 字典与预设同源）
- `docs/api.md` —— 接口参考
