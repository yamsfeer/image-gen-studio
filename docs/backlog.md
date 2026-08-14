# 功能待办（Backlog）

> 讨论中确定的「以后再做」的功能清单，按优先级排序。做完一项打勾并指向相关 ADR / 提交。
> 当前只落地了「分辨率 + 宽高比」两档参数（见 `adr/0002`），其余都记在这里，免得遗忘。

## 已确定但暂缓（Layer 2 任务 & 图片管理）

- [ ] **任务历史持久化**：内存 `TASKS` → SQLite 单文件（**已定方案：SQLite**，标准库自带，结构化查询方便）
- [ ] `GET /tasks?status=&model=&limit=&offset=` —— 任务列表 / 历史
- [ ] `POST /tasks/{id}/cancel` —— 取消排队/运行中的任务（对接 ComfyUI `/interrupt` + `/queue` 删除）
- [ ] `DELETE /tasks/{id}` —— 删除任务记录
- [ ] `GET /tasks/{id}/images` —— 批量返回任务所有图（带 seed / 参数 / 耗时元数据）
- [ ] **历史画廊**：前端可浏览过往生成结果（依赖上面持久化）

## 进阶生成能力（Layer 3）

- [ ] `POST /img2img` —— 图生图（需给每个模型补 img2img 工作流，工作量较大）
- [ ] `POST /inpaint` —— 局部重绘（带 mask）
- [ ] `POST /upscale` —— 高清放大（hires-fix / 放大模型）
- [ ] `POST /prompt/enhance` —— 提示词增强 / 翻译（需外部 LLM，后置）

## 可观测性 & 联调（Layer 4）

- [ ] `GET /health` —— 服务 + ComfyUI 连通性自检
- [ ] SSE / WebSocket 进度推送 —— 替代前端轮询做实时进度条（后端内部 WS 监听器已有，可对外透出）

## 有意「隐藏」的进阶参数（面向小白，暂不暴露）

- [ ] `seed` 手动控制（当前后端随机，不渲染；`capabilities.seed_control = false`）
- [ ] LoRA 叠加（`loras: [{name, strength}]`）
- [ ] sampler / scheduler 手动选择（当前用模型默认值）
- [ ] 以上放开路径：`adr/0002` 的 `capabilities` flag 翻 `true` + 前端按 `/presets` 自动渲染
