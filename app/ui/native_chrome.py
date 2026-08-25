"""原生窗口 chrome 适配 — Windows 标题栏深色模式

PySide6 自绘的 QSS 只管 App 自己的内容区,Windows 原生标题栏(带"最小化/
最大化/关闭"按钮的那条横条)由 DWM 单独画。要让它跟 App 的深色 QSS 融
为一体,得调 DWM API 设 DWMWA_USE_IMMERSIVE_DARK_MODE。

非 Windows 平台全部走 no-op。
"""
from __future__ import annotations
import sys


# DWM attribute 编号:
#   20 = Win10 1903+ 推荐的 immersive 模式
#   19 = Win10 早期版本/某些 Win11 build 的回退
_DWMWA_IMMERSIVE_DARK = 20
_DWMWA_IMMERSIVE_DARK_OLD = 19


def _set_titlebar_dark_win32(hwnd: int, dark: bool) -> bool:
    """通过 ctypes 调 DwmSetWindowAttribute。成功返回 True。"""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        dwmapi = ctypes.WinDLL("dwmapi")
        DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
        DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        DwmSetWindowAttribute.restype = ctypes.c_long

        value = ctypes.c_int(1 if dark else 0)
        # 优先新 API,失败回落旧 API
        hr = DwmSetWindowAttribute(
            hwnd,
            _DWMWA_IMMERSIVE_DARK,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        if hr != 0:
            hr = DwmSetWindowAttribute(
                hwnd,
                _DWMWA_IMMERSIVE_DARK_OLD,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        return hr == 0
    except Exception as e:  # noqa: BLE001
        print(f"[native_chrome] DWM 调用失败: {e}")
        return False


def apply_titlebar_theme(widget, theme: str) -> None:
    """把 widget 所在窗口的原生标题栏染成 dark/light。

    非 Windows 平台 / 离屏渲染 / 未 show 的 widget 都会优雅 no-op,
    不会抛异常打断启动。
    """
    if widget is None or sys.platform != "win32":
        return
    try:
        # 拿原生窗口句柄。effectiveWinId 在 widget 已经 show 之后才有效
        hwnd = int(widget.effectiveWinId())
    except Exception:
        return
    dark = (theme == "dark")
    _set_titlebar_dark_win32(hwnd, dark)
