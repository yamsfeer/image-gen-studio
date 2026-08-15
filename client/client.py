#!/usr/bin/env python3
"""生图服务客户端库 —— 唯一的 API 客户端实现，CLI 与 webui 共用。

作为库导入（从仓库根）：
    from client.client import ImageClient, ApiError
    c = ImageClient.from_env()              # 从 .env / 环境变量读取连接信息
    c = ImageClient("http://localhost:8080", "comfy", "密码")
    task = c.generate("qwen-image", "一只猫")
    c.wait(task["task_id"])                 # 轮询到完成
    c.download(task["task_id"], "cat.png")  # 下载图片

作为命令行：
    cd client && python3 client.py generate --model qwen-image --prompt "一只猫"
    python3 client.py task <task_id>
    python3 client.py download <task_id> -o out.png
    python3 client.py stats
"""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error


def _load_env_file(path):
    """极简 .env 加载器（KEY=VALUE，支持 # 注释；不覆盖已存在的环境变量）。

    与 webui/config.py 中的实现保持一致；如需更复杂语法可改用 python-dotenv。
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


# 依次加载：项目根 .env → client/.env（后者可覆盖根配置）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # client 的上一级 = 项目根
_load_env_file(os.path.join(_ROOT, ".env"))
_load_env_file(os.path.join(_HERE, ".env"))


def _env(*names, default=""):
    """按优先级取第一个存在的环境变量。"""
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return default


# 默认连接参数（命令行参数 / ImageClient.from_env 共用）
API_BASE_DEFAULT = _env("API_BASE", "IMAGE_API_BASE", default="http://localhost:8080")
API_USER_DEFAULT = _env("API_USER", "IMAGE_API_USER", default="comfy")
API_PASSWORD_DEFAULT = _env("API_PASSWORD", "IMAGE_API_PASSWORD", default="")


class ApiError(Exception):
    """后端不可达或返回错误时抛出，message 可直接展示给用户。"""


class ImageClient:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip("/")
        self.auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    @classmethod
    def from_env(cls):
        """从环境变量/.env 构造：API_BASE / API_USER / API_PASSWORD。"""
        return cls(API_BASE_DEFAULT, API_USER_DEFAULT, API_PASSWORD_DEFAULT)

    def _req(self, path: str, data=None, timeout=60) -> bytes:
        req = urllib.request.Request(self.base + path,
                                     method="POST" if data is not None else "GET")
        req.add_header("Authorization", f"Basic {self.auth}")
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

    def _json(self, path: str, data=None, timeout=60):
        return json.loads(self._req(path, data, timeout))

    # ---- 接口 ----
    def models(self):
        return self._json("/models")

    def stats(self):
        return self._json("/status")

    def generate(self, model: str, prompt: str, negative_prompt: str = "",
                 width: int = 1024, height: int = 1024, steps: int = 30,
                 cfg: float = 4.0, seed: int = None, batch_size: int = 1,
                 sampler: str = None, scheduler: str = None, timeout=60):
        if seed is None:
            seed = int(time.time())
        body = {"model": model, "prompt": prompt, "negative_prompt": negative_prompt,
                "width": width, "height": height, "steps": steps, "cfg": cfg,
                "seed": seed, "batch_size": batch_size}
        if sampler:
            body["sampler"] = sampler
        if scheduler:
            body["scheduler"] = scheduler
        return self._json("/tasks", body, timeout=timeout)

    def task(self, task_id: str):
        return self._json(f"/tasks/{task_id}", timeout=30)

    def wait(self, task_id: str, poll=5, timeout=1800):
        """轮询直到完成/出错，返回最终任务状态"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.task(task_id)
            if st["status"] in ("done", "error"):
                return st
            time.sleep(poll)
        raise TimeoutError(f"任务 {task_id} 超时")

    def image_bytes(self, task_id: str, index: int = 0, timeout=60) -> bytes:
        """下载任务产出的 PNG 二进制。"""
        return self._req(f"/tasks/{task_id}/images/{index}", timeout=timeout)

    def download(self, task_id: str, output: str, index: int = 0, timeout=60):
        """下载 PNG 并保存到本地文件，返回文件路径。"""
        data = self.image_bytes(task_id, index, timeout)
        with open(output, "wb") as f:
            f.write(data)
        return output


def main():
    p = argparse.ArgumentParser(description="生图服务客户端")
    p.add_argument("--base", default=API_BASE_DEFAULT)
    p.add_argument("--user", default=API_USER_DEFAULT)
    p.add_argument("--password", default=API_PASSWORD_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--model", default="qwen-image")
    g.add_argument("--prompt", required=True)
    g.add_argument("--negative", default="")
    g.add_argument("--width", type=int, default=1024)
    g.add_argument("--height", type=int, default=1024)
    g.add_argument("--steps", type=int, default=30)
    g.add_argument("--cfg", type=float, default=4.0)
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--batch", type=int, default=1)
    g.add_argument("--wait", action="store_true", help="提交后轮询到完成")
    g.add_argument("-o", "--output", default=None, help="完成后的下载路径")

    t = sub.add_parser("task")
    t.add_argument("task_id")
    sub.add_parser("stats")
    sub.add_parser("models")
    d = sub.add_parser("download")
    d.add_argument("task_id")
    d.add_argument("-o", "--output", default=None)
    d.add_argument("--index", type=int, default=0)

    args = p.parse_args()
    c = ImageClient(args.base, args.user, args.password)

    try:
        if args.cmd == "models":
            for m in c.models()["models"]:
                print(f"{m['id']:15s} {m['name']}  ({m.get('description','')})")
        elif args.cmd == "stats":
            print(json.dumps(c.stats(), ensure_ascii=False, indent=2))
        elif args.cmd == "task":
            print(json.dumps(c.task(args.task_id), ensure_ascii=False, indent=2))
        elif args.cmd == "download":
            out = args.output or f"img_{args.task_id[:8]}_{args.index}.png"
            print("保存到", c.download(args.task_id, out, args.index))
        elif args.cmd == "generate":
            r = c.generate(args.model, args.prompt, args.negative, args.width,
                           args.height, args.steps, args.cfg, args.seed, args.batch)
            print(f"已提交 task_id={r['task_id']} status={r['status']}")
            if args.wait:
                st = c.wait(r["task_id"])
                print(f"最终状态: {st['status']} 耗时 {st.get('elapsed_seconds')}s")
                if st["images"] and args.output:
                    print("保存到", c.download(r["task_id"], args.output))
                    print("图片 URL:", [f"{args.base}{u}" for u in st["images"]])
    except ApiError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
