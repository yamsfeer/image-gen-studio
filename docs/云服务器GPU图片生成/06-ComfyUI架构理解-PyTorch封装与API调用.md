# 06-ComfyUI架构理解：PyTorch的封装与API调用

> 2026-08 记录。把 ComfyUI 看透：它是什么、怎么调用、API 长什么样。

## 核心认知

**ComfyUI = 别人写好的 PyTorch 封装工具。** 底层就是 Python + PyTorch 操作模型，自己写代码能做同样的事，但 ComfyUI 把加载模型、缓存、并发、错误处理都包好了。它不是另一个引擎，是同一原理下省事的现成实现。

**ComfyUI 是一个常驻服务器程序，有两种面孔：**
```
WebUI（浏览器可视化）          HTTP API（程序调用）
拖节点、连线、滑参数   ──同图──> 提交同样一份 JSON 节点图
```

**它做的关键优化：** 模型常驻显存（换提示词秒跑，不像脚本每次冷启动 10-30s）+ 节点级缓存（不变的部分自动跳过不重算）。GPU 计算速度和写代码相同，省的是外围开销。

## 三种调用方式对比

| 维度 | A: 写 Python 代码(diffusers) | B1/B2: ComfyUI |
|------|------------------------------|----------------|
| 单张计算速度 | 相同（底层同算子） | 相同 |
| 模型加载 | 每次运行重载（10-30s 冷启动） | 常驻显存 |
| 节点缓存 | 无 | 有 |
| 调参 | 改代码重跑 | 拖拽滑块实时预览 |
| 批量自动化 | 强（循环逻辑自由） | 中 |
| 复用生态 | 自己写 | 现成工作流拖入即用 |

**实用分工：** 日常探索/调参用 ComfyUI 工作流；批量生产/脚本化写代码；两者模型共用，切换无成本。

## HTTP API 调用流程

```
POST /prompt（提交 JSON 工作流）→ 返回 prompt_id
GET  /history/{prompt_id}（轮询）→ completed 后返回结果
结果里带 outputs 字段 → 直接列出图片文件名/目录（不用自己猜）
图片默认存 ComfyUI/output/（SaveImage 节点），或 GET /view?filename=xxx 取流
```

## POST /prompt 的 Body 结构

```
{
  "prompt": {                    ← ★核心：API 格式的工作流节点图
    "1": {"class_type": "DiffusersLoader", "inputs": {...}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {...}},
    ...
  },
  "client_id": "abc",            ← 可选：WebSocket 进度关联
  "extra_data": {...},           ← 可选：附带 UI 工作流信息
  "number": 4                    ← 可选：批量重复次数
}
```

工作流就在 prompt 字段里——"prompt" 在 ComfyUI 术语中特指 API 格式节点图。

## 节点图核心语法

**节点 = {class_type: 节点类型名, inputs: {参数 + 端口连接}}**

端口连接格式：`["节点id", 端口号]` = 把那个节点的第 N 个输出接进来。
整个 JSON 就是一张流程图，每个节点是独立函数，边是显式的张量传递。

## 术语辨析：workflow vs prompt

| 名称 | 格式 | 用途 |
|------|------|------|
| workflow | nodes/links 数组（含坐标颜色） | 浏览器显示、png 内嵌、拖入 WebUI |
| prompt | 扁平 dict（id → {class_type, inputs}） | API 提交执行 |

**同一个流程，两种格式。** 网站下载的工作流 JSON 不能直接 POST，需转换（WebUI"Save (API Format)"）。之前下载的官方示例 png 内嵌的就是 workflow 格式。
