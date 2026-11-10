"""vinput.py —— AI 专用的"非实体鼠标键盘"。

设计目标（为什么要有这个模块）：
    真实鼠标键盘属于用户，AI 不应该去挪那唯一一个系统光标。
    Windows 单会话里只有**一个**系统光标、一个前台窗口，所以想让"AI 的鼠标"和
    "人的鼠标"同时各干各的，只有两条路：
      1) 不碰系统光标，把输入"定向投递"给指定窗口（本模块的 WindowTarget 后端）；
      2) 给 AI 一个独立会话/虚拟机（另一个光标，见 DESIGN 讨论，不在本模块）。

本模块提供一套"虚拟设备"接口：
    AIMouse(hwnd)      —— 鼠标：move / click / drag / wheel / hover
    AIKeyboard(hwnd)   —— 键盘：type_text / key / hotkey
    SessionMouse()     —— 需要真光标时（游戏/全屏）的兜底后端，走 SendInput

WindowTarget 后端用的是 PostMessage，**绝不移动用户的鼠标、不抢焦点**，
代价是：只对愿意接收窗口消息的普通程序有效（记事本、浏览器、Win32/WPF 应用），
对 DirectInput/原始输入的 3D 游戏（比如 SC2）无效。
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

u = ctypes.windll.user32

# —— 消息常量 ——
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_SYSKEYDOWN = 0x0104

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MI(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KI(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class IN(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", MI), ("ki", KI)]


def _lparam(x: int, y: int) -> int:
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def _post(hwnd, msg, wparam=0, lparam=0) -> bool:
    return bool(u.PostMessageW(hwnd, msg, wparam, lparam))


def window_title(hwnd) -> str:
    n = u.GetWindowTextLengthW(hwnd)
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def find_window(title_part: str, visible_only: bool = True):
    """按标题片段找顶层窗口，返回第一个命中的 hwnd（找不到返回 None）。"""
    hits = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if visible_only and not u.IsWindowVisible(hwnd):
            return True
        if title_part.lower() in window_title(hwnd).lower():
            hits.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    return hits[0] if hits else None


def client_rect(hwnd) -> tuple[int, int, int, int]:
    r = RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def hwnd_at(x: int, y: int):
    """某个屏幕坐标下真正接收鼠标的窗口（子控件级）。"""
    return u.WindowFromPoint(PT(x, y))


def windows_of(hwnd) -> list[tuple[int, str]]:
    """枚举一个窗口下的全部子控件：[(hwnd, class_name), ...]"""
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _lp):
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        out.append((h, buf.value))
        return True

    u.EnumChildWindows(hwnd, cb, 0)
    return out


def find_child_by_class(hwnd, class_name: str):
    """按类名片段找子控件（WinForms 的类名带哈希后缀，如
    'WindowsForms10.EDIT.app.0.d890cf_r13_ad1'，所以用包含匹配）。"""
    needle = class_name.lower()
    for h, cls in windows_of(hwnd):
        if needle in cls.lower():
            return h
    return None


def screen_to_client(hwnd, x: int, y: int) -> tuple[int, int]:
    pt = PT(x, y)
    u.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def screen_of(hwnd, cx: int, cy: int) -> tuple[int, int]:
    """客户区坐标 → 屏幕坐标。"""
    pt = PT(cx, cy)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


class AIMouse:
    """AI 自己的鼠标：定向投递到某个窗口，不动用户的系统光标。"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self._pressed = None

    # —— 坐标是相对目标窗口客户区的像素 ——
    def move(self, x: int, y: int) -> bool:
        return _post(self.hwnd, WM_MOUSEMOVE, 0, _lparam(x, y))

    def click(self, x: int, y: int, button: str = "left", double: bool = False, hold: float = 0.02) -> bool:
        down, up, mk, dbl = {
            "left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON, WM_LBUTTONDBLCLK),
            "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON, 0),
            "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON, 0),
        }[button]
        lp = _lparam(x, y)
        self.move(x, y)
        if double and dbl:
            _post(self.hwnd, dbl, mk, lp)
            time.sleep(0.02)
            _post(self.hwnd, dbl, mk, lp)
        else:
            _post(self.hwnd, down, mk, lp)
            time.sleep(hold)
            _post(self.hwnd, up, 0, lp)
        return True

    def press(self, x: int, y: int, button: str = "left") -> bool:
        msg, mk = {"left": (WM_LBUTTONDOWN, MK_LBUTTON), "right": (WM_RBUTTONDOWN, MK_RBUTTON)}[button]
        self._pressed = (x, y, button)
        return _post(self.hwnd, msg, mk, _lparam(x, y))

    def release(self) -> bool:
        if not self._pressed:
            return False
        x, y, button = self._pressed
        msg = WM_LBUTTONUP if button == "left" else WM_RBUTTONUP
        self._pressed = None
        return _post(self.hwnd, msg, 0, _lparam(x, y))

    def drag(self, x1: int, y1: int, x2: int, y2: int, steps: int = 8, hold: float = 0.01) -> bool:
        self.press(x1, y1)
        for i in range(1, steps + 1):
            self.move(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
            time.sleep(hold)
        return self.release()

    def wheel(self, delta: int, at: tuple[int, int] = (0, 0)) -> bool:
        """delta 为正向上滚。坐标为屏幕坐标（Windows 规矩）。"""
        return _post(self.hwnd, WM_MOUSEWHEEL, ((int(delta) & 0xFFFF) << 16), _lparam(*at))

    @staticmethod
    def click_screen(x: int, y: int, button: str = "left", double: bool = False):
        """按屏幕坐标点击：自动找到那个坐标下的窗口/控件再投递。

        这就是"AI 的鼠标指针"：坐标和真实点击一致，但系统光标不会动。
        返回 (hwnd, ok)。"""
        hwnd = hwnd_at(x, y)
        if not hwnd:
            return None, False
        cx, cy = screen_to_client(hwnd, x, y)
        return hwnd, AIMouse(hwnd).click(cx, cy, button, double)


class AIKeyboard:
    """AI 自己的键盘：定向投递按键到某个窗口。"""

    def __init__(self, hwnd):
        self.hwnd = hwnd

    def type_text(self, text: str, interval: float = 0.01) -> int:
        n = 0
        for ch in text:
            if _post(self.hwnd, WM_CHAR, ord(ch), 1):
                n += 1
            time.sleep(interval)
        return n

    def key(self, vk: int, interval: float = 0.02) -> bool:
        _post(self.hwnd, WM_KEYDOWN, vk, 1)
        time.sleep(interval)
        return _post(self.hwnd, WM_KEYUP, vk, 0xC0000001)

    def hotkey(self, *vks: int, interval: float = 0.03) -> bool:
        for vk in vks:
            _post(self.hwnd, WM_KEYDOWN, vk, 1)
            time.sleep(interval)
        for vk in reversed(vks):
            _post(self.hwnd, WM_KEYUP, vk, 0xC0000001)
            time.sleep(interval)
        return True


class SessionMouse:
    """兜底后端：真的动系统光标（走 SendInput）。

    只在"目标窗口已经在前台"并且用户没在操作时使用；会移动用户的鼠标。
    """

    def __init__(self):
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

    def _send(self, extra_info: int = 0) -> int:
        inp = IN()
        inp.type = 0
        return u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(IN))

    @staticmethod
    def _norm(x: int, y: int) -> tuple[int, int]:
        vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        cw, ch = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
        return int((x - vx) * 65535 / cw), int((y - vy) * 65535 / ch)

    def move(self, x: int, y: int) -> None:
        ax, ay = self._norm(x, y)
        inp = IN()
        inp.type = 0
        inp.mi.dx, inp.mi.dy = ax, ay
        inp.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(IN))

    def click(self, x: int, y: int, button: str = "left") -> None:
        self.move(x, y)
        flags = (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left" else (
            MOUSEEVENTF_RIGHTDOWN,
            MOUSEEVENTF_RIGHTUP,
        )
        for f in flags:
            inp = IN()
            inp.type = 0
            inp.mi.dwFlags = f
            u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(IN))
            time.sleep(0.02)


def user_idle_seconds() -> float:
    """用户已经多少秒没碰键盘鼠标了（判断能不能安全注入）。"""

    class LII(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    li = LII()
    li.cbSize = ctypes.sizeof(LII)
    if not u.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    tick = int(ctypes.windll.kernel32.GetTickCount64())
    # dwTime 是 32 位毫秒计数，换算到 64 位 tick 的同一圈
    now32 = tick & 0xFFFFFFFF
    delta = (now32 - int(li.dwTime)) & 0xFFFFFFFF
    return delta / 1000.0


def input_target(hwnd):
    """给"打字/按键"找个更准的落点：窗口里有 EDIT 子控件就投给它，否则用窗口本身。"""
    return find_child_by_class(hwnd, "EDIT") or hwnd


class AICursor:
    """AI 自己**看得见**的光标：一个置顶、透明、点不穿的红色圆环。

    它不是系统光标：不能拖动、不接收点击（WS_EX_TRANSPARENT）、不抢焦点，
    只是告诉人"AI 现在指哪儿、点哪儿"。真实鼠标该在哪还在哪。

        cur = AICursor()
        cur.move_to(1200, 700)      # 移到屏幕坐标
        cur.click_at(1200, 700)     # 点一下用户看到的位置（同时在目标窗口投递点击）
        cur.hide() / cur.close()
    """

    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080
    GWL_EXSTYLE = -20

    def __init__(self, size: int = 48, color: str = "#ff2d55", alpha: float = 0.95):
        import queue
        import threading

        self.size = size
        self.color = color
        self.alpha = alpha
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready = threading.Event()
        self._ready.wait(timeout=3)

    # —— 给调用方的接口（线程安全）——
    def move_to(self, x: int, y: int) -> None:
        self._q.put(("move", x, y))

    def hide(self) -> None:
        self._q.put(("hide",))

    def close(self) -> None:
        self._q.put(("close",))

    def click_at(self, x: int, y: int, hold: float = 0.25) -> None:
        self._q.put(("pulse",))
        self.move_to(x, y)
        time.sleep(hold)

    # —— UI 线程 ——
    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.alpha)
        root.attributes("-transparentcolor", "#010203")
        root.configure(bg="#010203")

        c = tk.Canvas(root, width=self.size, height=self.size, bg="#010203",
                      highlightthickness=0, bd=0)
        c.pack()
        half = self.size // 2
        c.create_oval(4, 4, self.size - 4, self.size - 4, outline=self.color, width=3)
        c.create_oval(half - 3, half - 3, half + 3, half + 3, fill=self.color, outline="")
        c.create_line(half - 10, half, half - 4, half, fill=self.color, width=2)
        c.create_line(half + 4, half, half + 10, half, fill=self.color, width=2)
        c.create_line(half, half - 10, half, half - 4, fill=self.color, width=2)
        c.create_line(half, half + 4, half, half + 10, fill=self.color, width=2)

        root.update_idletasks()

        hwnd = root.winfo_id()
        ex = u.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
        u.SetWindowLongW(
            hwnd,
            self.GWL_EXSTYLE,
            ex | self.WS_EX_LAYERED | self.WS_EX_TRANSPARENT | self.WS_EX_NOACTIVATE | self.WS_EX_TOOLWINDOW,
        )
        root.withdraw()
        self._ready.set()

        def poll():
            try:
                while True:
                    cmd = self._q.get_nowait()
                    if cmd[0] == "move":
                        _, x, y = cmd
                        s = self.size
                        root.geometry(f"{s}x{s}+{int(x) - s // 2}+{int(y) - s // 2}")
                        root.deiconify()
                        root.lift()
                    elif cmd[0] == "hide":
                        root.withdraw()
                    elif cmd[0] == "close":
                        root.destroy()
                        return
            except Exception:
                pass
            root.after(16, poll)

        root.after(16, poll)
        root.mainloop()


# ————————————————— 命令行入口 —————————————————
# 用法（给 shell / 其他脚本调）：
#   python vinput.py list                       # 列出可见顶层窗口
#   python vinput.py children "记事本"           # 列出某个窗口的子控件
#   python vinput.py type "记事本" "hello"       # 往那个窗口打字（不碰光标）
#   python vinput.py key "记事本" 13            # 发一个虚拟键（13=回车）
#   python vinput.py click 1234 50 20           # 点 hwnd=1234 的客户区 (50,20)

def _cli(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    cmd = argv[0]
    if cmd == "list":
        rows = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _lp):
            if u.IsWindowVisible(hwnd):
                t = window_title(hwnd)
                if t.strip():
                    rows.append((hwnd, t))
            return True

        u.EnumWindows(cb, 0)
        for hwnd, t in rows:
            print(f"{hwnd}\t{t}")
        return 0

    if cmd == "children":
        hwnd = find_window(argv[1])
        if not hwnd:
            print(f"找不到窗口: {argv[1]}")
            return 2
        for h, cls in windows_of(hwnd):
            print(f"{h}\t{cls}")
        return 0

    if cmd == "type":
        hwnd = find_window(argv[1])
        if not hwnd:
            print(f"找不到窗口: {argv[1]}")
            return 2
        tgt = input_target(hwnd)
        n = AIKeyboard(tgt).type_text(argv[2])
        print(f"已投递 {n} 个字符到 hwnd={tgt}")
        return 0

    if cmd == "key":
        hwnd = find_window(argv[1])
        if not hwnd:
            print(f"找不到窗口: {argv[1]}")
            return 2
        vk = int(argv[2], 0)
        print(f"sent VK {vk} -> {AIKeyboard(hwnd).key(vk)}")
        return 0

    if cmd == "click":
        hwnd = int(argv[1], 0)
        print(f"click -> {AIMouse(hwnd).click(int(argv[2]), int(argv[3]))}")
        return 0

    if cmd == "cursor":
        from aicursor import AICursor as _Cur

        x, y = int(argv[1]), int(argv[2])
        hold = float(argv[3]) if len(argv) > 3 else 10.0
        size = int(argv[4]) if len(argv) > 4 else 56
        color = tuple(int(v) for v in argv[5].split(",")) if len(argv) > 5 else (255, 45, 85)
        cur = _Cur(size=size, color=color)
        cur.move_to(x, y)
        print(f"虚拟光标在 ({x},{y})，显示 {hold:.0f}s（真实鼠标不受影响）")
        t0 = time.time()
        while time.time() - t0 < hold:
            time.sleep(0.1)
        cur.close()
        return 0

    if cmd == "clickv":
        hwnd = int(argv[1], 0)
        ok, pos = click_visible(hwnd, int(argv[2]), int(argv[3]))
        print(f"可见点击 at {pos} -> {ok}")
        return 0

    print(f"未知命令: {cmd}")
    return 2


# —— 用 Win32 分层窗口版覆盖 tkinter 版（tk 的 -transparentcolor 在部分机器上失效）——
try:
    from aicursor import AICursor as AICursor  # noqa: F401
except Exception as _e:  # pragma: no cover
    import warnings

    warnings.warn(f"aicursor 加载失败，退回 tkinter 版: {_e}")


def click_visible(hwnd, x: int, y: int, *, button: str = "left", double: bool = False, linger: float = 0.45):
    """可见点击：圆环先移到目标点、脉冲一下，再把点击投递给窗口。

    x, y 是目标窗口的客户区坐标；圆环画在屏幕坐标上，和真实光标互不干扰。
    返回 (点击是否投递成功, 圆环所在屏幕坐标)。
    """
    sx, sy = screen_of(hwnd, x, y)
    ring = AICursor()
    try:
        ring.move_to(sx, sy)
        time.sleep(0.12)
        ring.pulse()
        ok = AIMouse(hwnd).click(x, y, button=button, double=double)
        ring.pulse()
        time.sleep(linger)
        return ok, (sx, sy)
    finally:
        ring.close()


if __name__ == "__main__":
    import sys

    sys.exit(_cli(sys.argv[1:]))
