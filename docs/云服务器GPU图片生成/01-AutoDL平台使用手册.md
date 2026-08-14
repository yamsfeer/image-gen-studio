# AutoDL 云 GPU 平台使用手册

> 基于一台 RTX 2080 Ti 实例（region-42）的实际观察整理，2026-08

## 这台实例的硬件

| 项目 | 配置 |
|------|------|
| GPU | NVIDIA GeForce RTX 2080 Ti，11GB 显存（Turing 架构） |
| CPU | 12 核 |
| 内存 | 40GB |
| 系统盘 | 30GB（`/`） |
| 数据盘 | 50GB（`/root/autodl-tmp`） |
| 驱动 | 580.105.08（驱动级 CUDA 13.0） |

## 目录体系：什么会丢、什么不丢（最重要）

| 目录 | 名称 | 速度 | 关机 | 重置系统 | 保存镜像 |
|------|------|------|------|----------|----------|
| `/` | 系统盘 | 一般 | ✅ 不丢 | ❌ **清空** | ✅ 随镜像保存 |
| `/root/autodl-tmp` | 数据盘 | 快 | ✅ 不丢 | ✅ **保留** | ❌ 不随镜像保存 |
| `/root/autodl-nas` | 网盘 | 慢 | ✅ | ✅ | ✅（多实例共享，可选） |
| `/root/autodl-fs` | 文件存储 | 一般 | ✅ | ✅ | ✅（多实例共享，可选） |

**核心记忆点**：

- **代码/配置放 `/root`**（跟着镜像走，换机器一键还原）
- **大文件/数据集/模型权重放 `/root/autodl-tmp`**（重置不丢，但保存镜像时不含它——想持久化得重新下载或挪到文件存储）
- **数据集优先用公共库**（见下），不占自己磁盘

## 公共数据集库（福利）

`/autodl-pub/data` 预置 **46 个经典数据集**，只读挂载、免费直接用：

ImageNet、COCO2017、VOCdevkit、cifar-10/100、cityscapes、KITTI、CelebA、ADE20K、nuScenes、waymo、BERT/RoBERTa 预训练模型、Aishell 语音库等。

引用路径：`/autodl-pub/data/<数据集名>`，省掉几十上百 GB 下载。

## 登录横幅（/etc/autodl-motd）在说什么

每次登录自动显示三块内容：

1. **目录说明表**（上文那张表，实时提示你数据该放哪）
2. **硬件体检**：CPU 核数、内存、GPU 型号、各盘剩余（从 cgroup 实时读取）
3. **三条红字注意事项**：
   - 系统盘小，大数据放数据盘/文件存储
   - 清理系统盘看官方文档（`autodl.com/docs/qa1`）
   - **长任务用 `screen` 开后台**——SSH 断了程序继续跑

## 预装环境（开箱即用）

| 组件 | 版本/配置 |
|------|-----------|
| Python | 3.12.3（miniconda base） |
| PyTorch | 2.8.0+cu128（**GPU 版，直接用**） |
| conda 源 | 清华 TUNA（`.condarc` 预配） |
| pip 源 | 阿里云（`mirrors.aliyun.com/pypi/simple` 预配） |
| 其他 | jupyter-lab、tensorboard 常驻（Autodl 面板配套） |

> 容器默认**不带 CUDA toolkit**（无 nvcc），但 PyTorch 的 cu128 wheel 自带 runtime，推理完全够用；只有需要编译 CUDA 扩展时才要装 toolkit。

## 学术加速（/etc/network_turbo）

**作用**：注入内网代理（10.0.0.11:12798），加速访问 **GitHub / HuggingFace**。

**用法**：`source /etc/network_turbo`，仅当前会话生效。

**⚠️ 关键注意**：

- 开启后 **pip/conda/阿里云等国内源会变慢**（流量被代理截走）——只在下载 GitHub/HF 资源时开，下完就关（关 = 重新开一个 SSH 会话）
- 代理的 `no_proxy` 已排除 modelscope、aliyuncs、tencentyun 等国内域名
- 仅限学术用途，不承诺稳定性

## SSH 连接经验

- 本机已配别名 `ssh seetacloud`（`~/.ssh/config`，密钥免密，端口 25622）
- **非交互式 SSH 不加载 `.bashrc`**：`ssh seetacloud 'opencode'` 会找不到命令，需交互登录或用 `bash -ic`
- 面板上有 JupyterLab，也可以直接当图形入口用

## 一句话使用习惯

**代码放 `/root` 随镜像走，大文件放 `/root/autodl-tmp` 永不丢，数据集用公共库，下 GitHub 东西临时开学术加速，长任务套 screen。**
