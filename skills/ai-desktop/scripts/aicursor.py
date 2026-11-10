"""aicursor.py —— AI 的虚拟光标（Win32 分层窗口版）。

为什么不用 tkinter：tk 的 `-transparentcolor` 在部分机器/显卡上直接失效，
画出来的窗口是"存在但看不见"。分层窗口 + UpdateLayeredWindow 走的是系统自带的
per-pixel alpha 合成，稳定且边缘抗锯齿。

这个窗口：
  - 置顶（WS_EX_TOPMOST）、不抢焦点（WS_EX_NOACTIVATE）；
  - 鼠标事件穿透（WS_EX_TRANSPARENT）—— 用户点它点不到，等于不存在；
  - 只有 AI 能移动它；系统的真实光标完全不受影响。
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

u = ctypes.windll.user32
gdi = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
ULW_ALPHA = 0x00000002
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# —— 句柄/指针参数必须显式声明，否则 64 位句柄会被截断成 32 位（窗口创建"成功"但画不出来）——
u.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
u.CreateWindowExW.restype = wintypes.HWND
u.GetDC.restype = wintypes.HDC
u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u.RegisterClassW.restype = wintypes.ATOM
u.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(wintypes.POINT),
    ctypes.POINTER(wintypes.SIZE),
    wintypes.HDC,
    ctypes.POINTER(wintypes.POINT),
    wintypes.DWORD,
    ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD,
]
u.UpdateLayeredWindow.restype = wintypes.BOOL
gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi.CreateCompatibleDC.restype = wintypes.HDC
gdi.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi.CreateDIBSection.restype = wintypes.HBITMAP
gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi.SelectObject.restype = wintypes.HGDIOBJ
gdi.DeleteDC.argtypes = [wintypes.HDC]
gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi.DeleteObject.restype = wintypes.BOOL
u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u.DestroyWindow.argtypes = [wintypes.HWND]
u.GetDC.argtypes = [wintypes.HWND]
k32.GetModuleHandleW.restype = wintypes.HMODULE


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _make_image(size: int, color: tuple[int, int, int], ss: int = 4):
    """画一个带抗锯齿的准星圆环，返回 RGBA 原图。"""
    from PIL import Image, ImageDraw

    n = size * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r, g, b = color
    pad = 2 * ss
    w = max(2 * ss, n // 14)
    # 先画一圈深色描边，浅色背景（白墙、亮网页）上也不会糊掉
    d.ellipse([pad - w // 3, pad - w // 3, n - pad + w // 3, n - pad + w // 3],
              outline=(18, 18, 22, 255), width=max(1, w // 2))
    d.ellipse([pad, pad, n - pad, n - pad], outline=(r, g, b, 255), width=w)
    c = n // 2
    rad = max(3 * ss, n // 12)
    d.ellipse([c - rad - w // 4, c - rad - w // 4, c + rad + w // 4, c + rad + w // 4],
              fill=(18, 18, 22, 255))
    d.ellipse([c - rad, c - rad, c + rad, c + rad], fill=(r, g, b, 255))
    tick = w * 2
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        d.line(
            [c + dx * (n // 2 - pad - tick), c + dy * (n // 2 - pad - tick),
             c + dx * (n // 2 - pad), c + dy * (n // 2 - pad)],
            fill=(r, g, b, 255),
            width=max(1, w // 2),
        )
    return img.resize((size, size), Image.LANCZOS)


class AICursor:
    """看得见、点不穿的 AI 光标。坐标一律是**屏幕坐标**（多屏用虚拟桌面坐标）。"""

    _cls_registered = False
    _instances: list["AICursor"] = []

    def __init__(self, size: int = 56, color: tuple[int, int, int] = (255, 45, 85), alpha: int = 240):
        self.size = size
        self.color = color
        self.alpha = alpha
        self._visible = False
        self._x, self._y = -10_000, -10_000

        if not AICursor._cls_registered:
            u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            u.DefWindowProcW.restype = ctypes.c_ssize_t
            self._proc_ref = WNDPROC(lambda h, m, w, l: int(u.DefWindowProcW(h, m, w, l)))
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._proc_ref
            wc.hInstance = k32.GetModuleHandleW(None)
            wc.lpszClassName = "DshAICursorWnd"
            u.RegisterClassW(ctypes.byref(wc))
            AICursor._cls_registered = True

        self.hwnd = u.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            "DshAICursorWnd",
            "AI-Cursor",
            WS_POPUP,
            0, 0, size, size,
            None, None, k32.GetModuleHandleW(None), None,
        )

        self._img = _make_image(size, color)
        self._hdc_screen = u.GetDC(None)
        self._memdc = gdi.CreateCompatibleDC(self._hdc_screen)
        self._build_bitmap()
        self._blend = BLENDFUNCTION(0, 0, alpha, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        self._pump_thread = threading.Thread(target=self._pump, daemon=True)
        self._running = True
        self._pump_thread.start()

    # —— 位图 ——
    def _build_bitmap(self) -> None:
        w = h = self.size
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # 自上而下
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        self._bits = ctypes.c_void_p()
        self._hbitmap = gdi.CreateDIBSection(
            self._memdc, ctypes.byref(bmi), 0, ctypes.byref(self._bits), None, 0
        )
        gdi.SelectObject(self._memdc, self._hbitmap)

        # 预乘 alpha 的 BGRA
        buf = (ctypes.c_ubyte * (w * h * 4)).from_address(self._bits.value)
        px = self._img.load()
        i = 0
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                buf[i] = (b * a) // 255
                buf[i + 1] = (g * a) // 255
                buf[i + 2] = (r * a) // 255
                buf[i + 3] = a
                i += 4

    def _blit(self, x: int, y: int) -> None:
        dst = wintypes.POINT(int(x) - self.size // 2, int(y) - self.size // 2)
        src = wintypes.POINT(0, 0)
        sz = wintypes.SIZE(self.size, self.size)
        u.UpdateLayeredWindow(
            self.hwnd,
            self._hdc_screen,
            ctypes.byref(dst),
            ctypes.byref(sz),
            self._memdc,
            ctypes.byref(src),
            0,
            ctypes.byref(self._blend),
            ULW_ALPHA,
        )

    # —— 消息泵（分层窗口也要及时处理消息，否则会被系统当成卡死）——
    def _pump(self) -> None:
        msg = wintypes.MSG()
        while self._running:
            got = False
            while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
                got = True
            if not got:
                time.sleep(0.01)

    # —— 对外接口 ——
    def move_to(self, x: int, y: int) -> None:
        self._x, self._y = int(x), int(y)
        self._blit(x, y)
        if not self._visible:
            u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self._visible = True

    def pulse(self) -> None:
        """点一下的视觉反馈：缩小再弹回。"""
        for s in (0.75, 0.9, 1.0):
            self._blend.SourceConstantAlpha = int(self.alpha * s)
            self._blit(self._x, self._y)
            time.sleep(0.05)
        self._blend.SourceConstantAlpha = self.alpha
        self._blit(self._x, self._y)

    def hide(self) -> None:
        u.ShowWindow(self.hwnd, SW_HIDE)
        self._visible = False

    def close(self) -> None:
        self._running = False
        u.ShowWindow(self.hwnd, SW_HIDE)
        u.DestroyWindow(self.hwnd)
        gdi.DeleteObject(self._hbitmap)
        gdi.DeleteDC(self._memdc)
        u.ReleaseDC(None, self._hdc_screen)
