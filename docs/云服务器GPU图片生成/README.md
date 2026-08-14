# 云服务器 GPU 图片生成

> 用云服务器显卡跑 AI 图片生成的全过程记录。AutoDL RTX 2080 Ti 实例。

## 文章索引

| 文章 | 内容 |
|------|------|
| [[01-AutoDL平台使用手册]] | 平台目录体系（什么丢/什么不丢）、预装环境、学术加速、SSH 经验 |
| [[02-云服务器GPU图片生成部署全记录]] | diffusers → ComfyUI 两条路线、LCM 加速、性能对比、5 个踩坑与解法 |
| [[03-MiniMax-H3视频生成本地部署调研]] | H3 视频+音频全模态模型调研：显存需求、能否本地跑、优化方向 |
| [[04-ComfyUI与模型推理生态地图]] | 两张生态地图：ComfyUI 三类资产去哪找、推理加速工具全谱系 |
| [[05-推理加速原理-TensorRT与SageAttention]] | 以两个知名工具讲清推理加速原理：算子融合、注意力量化、架构绑定 |
| [[06-ComfyUI架构理解-PyTorch封装与API调用]] | ComfyUI 是 PyTorch 的封装：HTTP API 调用流程、节点图 JSON 语法、workflow vs prompt |

> 网络相关笔记已移入 `网络知识/` 专题文件夹：[[网络基础：如何让别人访问你的服务]]

## 当前状态（2026-08）

- ✅ CUDA + PyTorch + 模型 + 出图全链路跑通
- ✅ ComfyUI 0.31 常驻服务（LCM 4 步，0.75s/张，批量 1.33 张/秒）
- ⏳ 待做：TensorRT 引擎加速、SDXL 高画质、批量生产脚本打磨

## 服务器速查

```
ssh seetacloud
cd /root/autodl-tmp/ComfyUI && python main.py --listen 127.0.0.1 --port 8188   # 启动
python /root/gen_image.py "prompt" output.png                                   # diffusers 直调
```
