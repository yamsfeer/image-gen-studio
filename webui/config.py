"""全局配置：API 地址、认证凭据、轮询间隔。

配置优先级（高 → 低）：
    1. 环境变量（API_BASE / API_USER / API_PASSWORD；兼容旧名 IMAGE_API_*）
    2. 项目根目录 .env 或 webui/.env 文件
    3. 代码内默认值

运行：
    python webui/app.py    # 默认 http://127.0.0.1:7860
"""
import os


def _load_env_file(path):
    """极简 .env 加载器（KEY=VALUE，支持 # 注释；不覆盖已存在的环境变量）。

    与 client/client.py 中的实现保持一致；如需更复杂的 .env 语法
    （插值、多行值等），可改用 python-dotenv。
    """
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


# 依次加载：项目根 .env → webui/.env（后者可覆盖根配置）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # webui 的上一级 = 项目根
_load_env_file(os.path.join(_ROOT, ".env"))
_load_env_file(os.path.join(_HERE, ".env"))


def _get(*names, default=""):
    """按优先级取第一个存在的环境变量。"""
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return default


API_BASE = _get("API_BASE", "IMAGE_API_BASE", default="http://localhost:8080")
API_USER = _get("API_USER", "IMAGE_API_USER", default="comfy")
API_PASSWORD = _get("API_PASSWORD", "IMAGE_API_PASSWORD", default="")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "3"))       # 生图任务轮询间隔（秒）
STATS_INTERVAL = int(os.environ.get("STATS_INTERVAL", "10"))    # GPU 状态刷新间隔（秒）

# 高级参数可选值（对齐 ComfyUI 与后端 /models 默认值）
SAMPLERS = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde",
            "dpmpp_sde", "ddim", "uni_pc", "res_multistep"]
SCHEDULERS = ["normal", "karras", "exponential", "sgm_uniform", "simple",
              "ddim_uniform", "beta"]

# 图片落地目录（供下载按钮引用）
DOWNLOAD_DIR = os.path.join(_HERE, "downloads")
