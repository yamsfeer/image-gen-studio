"""加载并查询 presets.json 里的预设配置。"""
import json
import os

_PRESETS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "presets.json")

_cache = None


def _load() -> list:
    global _cache
    if _cache is None:
        with open(_PRESETS_FILE, encoding="utf-8") as f:
            _cache = json.load(f)["presets"]
    return _cache


def get_presets() -> list:
    return _load()


def find_preset(preset_id: str) -> dict:
    for p in _load():
        if p["id"] == preset_id:
            return p
    return None


def dropdown_choices() -> list:
    """返回 [(显示文本, 值)]，供 gr.Dropdown 直接使用。"""
    return [(p["label"], p["id"]) for p in _load()]
