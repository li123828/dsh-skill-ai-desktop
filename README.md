# AI Desktop — a virtual mouse & keyboard that belongs to the agent

Give DeepSeek Harness an input channel that **never steals your mouse**: the agent posts clicks and keystrokes straight into a target window (`PostMessage`), so the system cursor and the foreground window stay exactly where you left them. Plus a click-through ring cursor so you can see where the agent is clicking.

- Backend: Win32 `PostMessage` (`WM_LBUTTONDOWN/UP`, `WM_KEYDOWN`, `WM_CHAR`)
- No third-party deps (Python stdlib + Pillow for the cursor; falls back to a solid dot)
- No admin rights, no `danger-full-access` needed
- Verified on Windows 11: text reaches a non-foreground EDIT control character by character, clicks land, `GetCursorPos` unchanged

## Install

A skill is just a directory containing `SKILL.md`:

```powershell
git clone https://github.com/<you>/dsh-skill-ai-desktop
# workspace-scoped
Copy-Item -Recurse dsh-skill-ai-desktop\skills\ai-desktop .dsh\skills\
# or global profile
Copy-Item -Recurse dsh-skill-ai-desktop\skills\ai-desktop "$env:USERPROFILE\.dsh\skills\"
```

Or run `install.ps1 -Scope workspace|profile`. Start a **new session** afterwards (skills are scanned at session start), and the `ai-desktop` skill becomes available.

## 30-second check

```powershell
cd <skill dir>\scripts
python vinput.py list                  # windows are listed -> handles & permissions fine
python vinput.py cursor 900 300 10 96  # a 96px ring shows up for 10s -> cursor path fine
```

## Usage

```python
from vinput import find_window, AIKeyboard, AIMouse, click_visible
hwnd = find_window("Notepad")
AIKeyboard(hwnd).type_text("hello world")
AIMouse(hwnd).click(120, 60)     # client coordinates; system cursor untouched
click_visible(hwnd, 120, 60)     # the click is visible to the human
```

See `skills/ai-desktop/SKILL.md` for the full API, pitfalls and safety rules.

## Why not SendInput

`SendInput` drives the single system cursor and foreground window: the agent moving the mouse takes it away from you, and your movement redirects its clicks. Worse, under DSH's default low-integrity token those calls succeed but do nothing. `PostMessage` targets a window directly, so both of you can work at the same time.

## License

MIT
