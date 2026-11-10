# AI Desktop — AI 专属的虚拟键鼠

给 DSH 一个**不抢你鼠标**的输入通道：AI 向指定窗口定向发送点击与键盘，系统光标和前台窗口完全不动；再加一个**点击穿透的圆环光标**，让你看得见 AI 点在哪里。

- 后端：Win32 `PostMessage`（`WM_LBUTTONDOWN/UP`、`WM_KEYDOWN/WM_CHAR`）
- 无第三方依赖：只有 Python 标准库 + Pillow（画光标用，缺失时回退纯色块）
- 无需管理员权限、无需 `danger-full-access`
- 已验证：非前台窗口的 EDIT 控件收字逐字到达、点击命中、`GetCursorPos` 前后一致

## 安装

技能就是「一个含 `SKILL.md` 的目录」，两种装法：

```powershell
# A. 装到当前工作区（只对这个项目生效）
git clone https://github.com/<you>/dsh-skill-ai-desktop
New-Item -ItemType Directory -Force .dsh\skills | Out-Null
Copy-Item -Recurse dsh-skill-ai-desktop\skills\ai-desktop .dsh\skills\

# B. 装到全局 profile（所有项目可用）
Copy-Item -Recurse dsh-skill-ai-desktop\skills\ai-desktop "$env:USERPROFILE\.dsh\skills\"
```

也可以直接跑 `install.ps1 -Scope workspace|profile`（自动挑目录并校验 Python）。

装完**新开一个会话**（技能目录在会话启动时扫描），模型就能看到 `ai-desktop`。

## 30 秒验证

```powershell
cd <skill 目录>\scripts
python vinput.py list                     # 能列出窗口 = 权限和句柄没问题
python vinput.py cursor 900 300 10 96     # 屏幕上出现 96px 黄环 10 秒 = 光标通路 OK
```

## 参考

```python
from vinput import find_window, AIKeyboard, AIMouse, click_visible
hwnd = find_window("记事本")
AIKeyboard(hwnd).type_text("hello 世界")
AIMouse(hwnd).click(120, 60)      # 客户区坐标；系统光标不动
click_visible(hwnd, 120, 60)      # 用户能看见点击位置
```

完整 API、坑与安全规则见 `skills/ai-desktop/SKILL.md`。

## 为什么不用 SendInput

`SendInput` 操作的是系统唯一光标与前台窗口——AI 一动就抢用户的鼠标；而且 DSH 默认的低完整性令牌下注入会被静默吞掉（返回成功但无效）。`PostMessage` 直接找窗口投递，用户和 AI 互不干扰。

## License

MIT
