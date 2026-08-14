# 0001 后端 API 基线盘点

状态: 已接受
日期: 2026-08-14

## 背景 / 动机

在扩展后端功能之前，先固化「现在有什么、边界在哪」，作为后续所有接口设计决策的
基线（baseline）。避免在无共识的情况下各写各的接口。

## 决策

当前服务层（`server/service.py`）对外暴露 **6 个接口**，全部走 nginx 8080 + Basic Auth，
ComfyUI(8188) 不对外暴露，由服务层内部直连：

| # | 方法 & 路径 | 含义 | 备注 |
|---|---|---|---|
| 1 | `GET /` | 服务自检 | 返回服务名、模型列表、docs 链接 |
| 2 | `GET /models` | 列出模型及默认参数 | 供前端渲染模型选择；`builder` 字段已剥离 |
| 3 | `POST /generate` | 提交生图任务（异步） | 校验参数 → 构造工作流 → 提交 ComfyUI，立即返回 `task_id` |
| 4 | `GET /task/{task_id}` | 轮询任务状态 | 排队位置 / 实时进度 / 完成图片 URL / 错误 |
| 5 | `GET /image/{task_id}?index=N` | 下载第 N 张图 | 从 ComfyUI `/view` 直读 PNG |
| 6 | `GET /stats` | GPU + 队列 + 任务统计 | `nvidia-smi` + ComfyUI `/queue` |

### 关键设计约束（后续决策必须遵守）

1. **异步任务模型**：`/generate` 立即返回，前端靠 `/task/{id}` 轮询。
   状态机 `submitted → queued → running → done/error`。
2. **无状态服务层**：`TASKS` 是内存字典，服务重启即丢（重启 2 秒、不影响 ComfyUI）。
3. **参数校验集中在后端**：`service.py` 内联校验宽高/步数/cfg/batch 范围，后端是唯一权威，
   前端只是辅助展示。
4. **模型 = 工作流构造器**：`server/workflows.py` 里每个模型对应一个 `builder`（构造 ComfyUI
   图）+ 一套 `defaults`（最佳参数）。`/models` 直接读这张注册表。
5. **ComfyUI 不直连外部**：图片经 `/view` 由服务层代取；进度经内部 WebSocket 监听器同步到任务表。

## 备选方案

- 直接把 ComfyUI 原生端点（`/prompt`、`/history`、`/view`、`/object_info`）经 nginx 暴露给前端
  → **否决**：会把 ComfyUI 的复杂度泄漏给前端，且需要额外鉴权/安全加固；服务层包装是更稳的边界。
- 同步接口（`/generate` 阻塞到出图）→ **否决**：单 GPU 并发下会占死请求线程，异步 + 轮询更适合排队场景。

## 影响 / 后果

- 前端能力当前被锁定在「选模型 + 填提示词 + 调少数参数 + 下载」这一最小闭环（见 `webui/`）。
- 若要给前端更多自定义能力（宽高比、种子、LoRA、图生图、历史画廊等），需在本基线之上
  新增接口，见后续 ADR（0002 起）。

## 关联

- 实现：`server/service.py`、`server/workflows.py`
- 文档：`docs/api.md`、`docs/server-status.md`
- 客户端：`client/client.py`
