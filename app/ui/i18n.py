"""国际化(i18n) — JSON 三语字典 + tr() 全局函数"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

_CURRENT = "zh"
_DICTS: dict[str, dict[str, str]] = {}


def i18n_dir() -> Path:
    """i18n JSON 资源目录(打包后 / 开发时兼容)"""
    # 开发模式: <root>/app/resources/i18n
    dev = Path(__file__).resolve().parent.parent / "resources" / "i18n"
    if dev.exists():
        return dev
    # 打包后(用户数据目录)
    from app.paths import app_data_dir
    return app_data_dir() / "i18n"


def load(lang: str) -> None:
    """加载指定语言;缺失 key 静默回退到 key 本身"""
    global _CURRENT
    _CURRENT = lang if lang in ("zh", "en", "ja") else "zh"
    _DICTS.clear()
    base = i18n_dir()
    for code in ("zh", "en", "ja"):
        path = base / f"{code}.json"
        if path.exists():
            try:
                _DICTS[code] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[i18n] Failed to load {code}: {e}")
                _DICTS[code] = {}


def current() -> str:
    return _CURRENT


def tr(key: str, **kwargs) -> str:
    """获取翻译文本;支持 {var} 占位符"""
    text = _DICTS.get(_CURRENT, {}).get(key)
    if text is None:
        # 回退到 zh,再回退到 key
        text = _DICTS.get("zh", {}).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def available_languages() -> list[dict[str, str]]:
    return [
        {"code": "zh", "name": "中文"},
        {"code": "en", "name": "English"},
        {"code": "ja", "name": "日本語"},
    ]
