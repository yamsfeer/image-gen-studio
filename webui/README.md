# Image Gen Studio Web UI（v1 · Gradio）

给后端生图服务（FastAPI + ComfyUI）做的 Web 界面：**预设选择 → 填提示词 → 点生成 → 看结果**。

前端只依赖 Python + Gradio，不依赖显卡；后端才需要 GPU。所以本目录**可独立运行**，连任意一个部署好的后端即可。

## 快速开始

```bash
# 0. 前置：有一个可达的后端（本机 SSH 隧道已建，或后端公网可达）
# 1. 安装依赖（建议用虚拟环境）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置后端地址与凭据（三选一）
#    a) 复制模板：cp webui/.env.example webui/.env 并填写
#    b) 或复用项目根 .env（cp ../.env.example ../.env）
#    c) 或用环境变量：export API_BASE=... API_USER=... API_PASSWORD=...

# 3. 启动
python3 webui/app.py
# → 打开 http://127.0.0.1:7860
```

配置优先级：**环境变量 > webui/.env > 项目根 .env > 代码默认值**。

## 连接任意后端

前端只认三个变量（定义在 `webui/config.py`）：

| 变量 | 说明 | 默认 |
|---|---|---|
| `API_BASE` | 后端地址 | `http://localhost:8080` |
| `API_USER` | Basic Auth 账号 | `comfy` |
| `API_PASSWORD` | Basic Auth 密码 | 空 |

- 想连本项目的云后端：本机建好 SSH 隧道后，`API_BASE=http://localhost:8080` 即可（默认值）。
- 想连别人部署好的后端：把 `API_BASE` 指向对方地址 + 填对方给的账号密码。

## 功能（对应 PLAN F1-F7）

| 功能 | 说明 |
|---|---|
| F1 预设选择 | 8 个预设（4 模型 × 2 工作流），下拉选择后自动填充参数并显示描述 |
| F2 提示词 | 主提示词（必填）+ 负面提示词（可选，Z-Image 模型自动忽略） |
| F3 高级参数 | 折叠面板：steps / cfg / seed / 宽高 / sampler / scheduler，默认跟随预设 |
| F4 生成与进度 | 点生成 → 提交任务 → 每 3s 轮询，显示排队位置 / 采样进度 / 耗时 |
| F5 结果 | 完成显示图片 + 下载按钮；失败红字显示原因 |
| F6 GPU 状态 | 右上角每 10s 刷新 /stats（显存 / 利用率 / 温度 / 队列） |
| F7 历史 | 会话内历史：参数明细表 + 图片缩略图（点击缩略图回看 + 下载） |

## 文件结构

```
webui/
├── app.py          # 入口
├── config.py       # API 地址 / 凭据 / 轮询间隔（读 .env + 环境变量）
├── api_client.py   # API 封装（generate / task / image / stats）
├── presets.py      # 加载 presets.json
├── presets.json    # 8 个预设参数（与 /generate 请求体对齐）
├── handlers.py     # 事件处理（预设填充 / 生成 / 轮询 / GPU / 历史）
├── ui.py           # Gradio 布局 + 事件绑定
├── downloads/      # 生成图片落地目录（供下载按钮引用）
└── tests/          # Playwright 自动化测试
```

## Playwright 自动化测试

用本机 Playwright（Chromium）驱动真实浏览器验证。需先启动 `app.py`。

```bash
python3 webui/tests/ui_test.py          # 冒烟：页面加载 + 元素探测
python3 webui/tests/interact_test.py    # 主流程：预设填充 + 端到端生成（SD15 最快）
python3 webui/tests/interact_test.py --no-generate   # 只测 UI 层（预设/参数填充）
python3 webui/tests/extra_test.py       # 边界：空提示词 + Z-Image 生成 + 历史回看
```

注意：交互测试会真实调用后端出图（每次约 3~30s），请确保后端可访问。

## 踩过的坑（gradio 6）

- **Gallery 的 value 必须是列表**：`[PIL]` 而不是单个 PIL，否则报 `TypeError: 'Image' object is not iterable`。
- **`elem_id` 在 Accordion 折叠内容里不生效**：测试改用 `data-testid`（`range-input`/`number-input`）定位。
- **Dataframe 动态更新后数据行 `visibility: collapse`**：用户可见但点击不触发 select，故历史回看改用 **Gallery 缩略图**（点击 `button.thumbnail-item`）。
- **gradio 6 事件数据**：回调要拿 `evt` 必须带类型注解 `evt: gr.SelectData`，gradio 才把它注入。
