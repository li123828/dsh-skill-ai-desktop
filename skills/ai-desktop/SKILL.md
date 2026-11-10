---
name: ai-desktop
description: AI 专属虚拟键鼠 + 看得见的 AI 光标。需要「在不抢用户鼠标的前提下操作某个窗口」时使用——向指定 hwnd 定向发送点击/键盘（PostMessage，系统光标与前台窗口都不动），并用 Win32 分层窗口在屏幕上画一个圆环光标，让用户看见 AI 点在哪里。适合批量填表、驱动没有命令行入口的 GUI、以及把自动化跑在副屏的同时让用户正常用主屏。
---

# AI 专属虚拟键鼠（Windows）

## 为什么不是 SendInput

`SendInput` / `SetCursorPos` 操作的是**系统唯一的光标和前台窗口**：AI 一动，用户的鼠标就被抢走，用户一动，AI 的点击就落到别处。而且 DSH 的命令默认跑在低完整性令牌里，注入会被静默吞掉（返回成功但无效）。

这里的做法是 **`PostMessage` 直投窗口消息**：不碰系统光标、不抢焦点、不需要提权，用户可以同时用真实鼠标干自己的事。

## 环境

- Windows 10/11，Python 3.9+（本机 3.13），无第三方依赖（只用 ctypes + PIL 画光标；PIL 缺失时回退纯色块）。
- 脚本在 `scripts/`，两个文件：`vinput.py`（输入）、`aicursor.py`（光标）。

## 三种用法

### 1) 命令行（最快验证）

```powershell
python scripts/vinput.py list                      # 列出可见窗口 + hwnd
python scripts/vinput.py children <hwnd>           # 列出子控件（找 EDIT / BUTTON 用）
python scripts/vinput.py click  <hwnd> 120 60      # 在客户区坐标点击（默认左键）
python scripts/vinput.py type   <hwnd> "你好 ABC"  # 定向输入文字
python scripts/vinput.py key    <hwnd> ENTER       # 单个键 / 组合键 CTRL+A
python scripts/vinput.py cursor 900 300 20 96 "255,221,0"   # 屏幕上显示 96px 黄环 20 秒
```

### 2) 作为库

```python
from vinput import find_window, AIMouse, AIKeyboard, click_visible, user_idle_seconds

hwnd = find_window("记事本")            # 模糊匹配标题
AIKeyboard(hwnd).type_text("hello 123")
AIMouse(hwnd).click(120, 60)            # 客户区坐标，不移动系统光标
click_visible(hwnd, 120, 60)            # 圆环飞过去 → 脉冲 → 点击 → 脉冲（用户看得见）
```

要点：

- **坐标是客户区坐标**（相对窗口左上角，不含标题栏）；屏幕坐标用 `click_screen(hwnd, sx, sy)`。
- `AIMouse.click` 的 `button` 是字符串 `"left" / "right" / "middle"`。
- 键盘消息走 `WM_KEYDOWN/WM_CHAR`；中文、emoji 请用 `type_text`（内部走 `WM_CHAR`，逐字符）。
- 目标程序如果是 **Electron / UWP / 全屏游戏**，`PostMessage` 可能被忽略——这时才退回 `SessionMouse`（真 SendInput），并提示用户“我短暂接管鼠标”。

### 3) 让用户看见 AI 在点哪

`aicursor.AICursor()` 创建 1 个 per-pixel alpha 的分层窗口（`WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOPMOST|WS_EX_NOACTIVATE`），画一个**点击穿透**的圆环：

```python
from aicursor import AICursor
with AICursor(size=96, color=(255, 221, 0)) as c:
    c.pulse(900, 300)      # 出现在坐标处并做一次缩放脉冲
```

注意（都踩过）：

- 分层窗口**不会**出现在 `ImageGrab` / BitBlt 的截图里，别用截图验证它；用 `IsWindowVisible` + `GetWindowRect` + `WindowFromPoint` 验证（后者返回下面的窗口 = 点击穿透正常）。
- 所有 Win32 调用必须显式声明 `argtypes` / `restype`，否则 64 位句柄被截成 32 位，表现为 `OverflowError: int too long to convert`。

## 安全规则（重要）

1. **先认窗口再动手**：`list` / `children` 确认真的是目标窗口；`PostMessage` 不看前台，打错 hwnd 就是静默打错地方。
2. **不碰系统级快捷键**：`Win` 键的合成消息被 Explorer 忽略，别拿它当“打开开始菜单”的手段。
3. **敏感窗口不碰**：密码框、支付、企业后台，一律让用户自己操作。
4. **批量操作先小样**：先点 1 次、打 1 行，再扩到循环；每次循环后校验一次结果（读回控件文本或截图对比）。
5. **用户正在忙就让路**：`user_idle_seconds() < 2` 时等待，别和真人抢输入。

## 已知边界

| 情况 | 结果 |
|---|---|
| 目标窗口最小化 | PostMessage 仍可送达，但控件可能不更新布局；先 `ShowWindow(SW_RESTORE)` |
| 目标程序要求真实输入（部分游戏/安控） | 会被忽略，需回退 SendInput + 明确告知用户 |
| 全屏独占应用 | 光标窗口被盖住（可用 `TOPMOST` 抢占，但别在游戏里这样做） |
| 多屏 | 光标用屏幕坐标即可，负数坐标表示左侧副屏 |
