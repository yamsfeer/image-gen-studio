"""后端生图 API 轻量封装：generate / task / image / stats / models。

逻辑参考 client/client.py，去掉了 CLI，改为适合在 Gradio 事件里
直接调用的形态。所有网络错误统一包装为 ApiError，方便 UI 层展示。
"""
import base64
import json
import time
import urllib.error
import urllib.request


class ApiError(Exception):
    """后端不可达或返回错误时抛出，message 可直接展示给用户。"""


class ImageClient:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip("/")
        self._auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    # ---------- 底层 ----------
    def _request(self, path: str, data=None, timeout: int = 60) -> bytes:
        req = urllib.request.Request(
            self.base + path, method="POST" if data is not None else "GET")
        req.add_header("Authorization", f"Basic {self._auth}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(data).encode()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"HTTP {e.code}: {body[:300]}") from e
        except urllib.error.URLError as e:
            raise ApiError(f"无法连接后端 {self.base}：{e.reason}") from e
        except OSError as e:
            raise ApiError(f"网络错误：{e}") from e

    def _json(self, path: str, data=None, timeout: int = 60):
        return json.loads(self._request(path, data, timeout))

    # ---------- 接口 ----------
    def models(self):
        return self._json("/models")

    def stats(self):
        return self._json("/stats", timeout=30)

    def generate(self, model: str, prompt: str, negative_prompt: str = "",
                 width: int = 1024, height: int = 1024, steps: int = 30,
                 cfg: float = 4.0, seed=None, sampler: str = None,
                 scheduler: str = None, timeout: int = 60) -> dict:
        """提交生图任务，立即返回 {"task_id": ..., "status": ...}。

        seed 传 None / -1 / 空串 时用当前时间戳（后端缺省行为）。
        """
        if seed in (None, "", -1, "-1"):
            seed = int(time.time())
        body = {
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": int(width),
            "height": int(height),
            "steps": int(steps),
            "cfg": float(cfg),
            "seed": int(seed),
            "batch_size": 1,
        }
        if sampler:
            body["sampler"] = sampler
        if scheduler:
            body["scheduler"] = scheduler
        return self._json("/generate", body, timeout=timeout)

    def task(self, task_id: str) -> dict:
        return self._json(f"/task/{task_id}", timeout=30)

    def image_bytes(self, task_id: str, index: int = 0, timeout: int = 60) -> bytes:
        """下载任务产出的 PNG 二进制。"""
        return self._request(f"/image/{task_id}?index={index}", timeout=timeout)
