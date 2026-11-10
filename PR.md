# 上架 submission（ame 到 awesome-dsh-plugin）

> 目标仓库：`github.com/awesome-dsh-plugin/awesome-dsh-plugin`（市场的插件列表就来自这里，加一条 → 站点与市场自动收录，通常一天内生效）

## PR 标题

`Add ai-desktop skill: agent-owned virtual mouse & keyboard for Windows`

## PR 正文

```markdown
### 是什么

`ai-desktop` 是一个 DSH 技能：给 agent 一条**不抢用户鼠标**的输入通道，外加一个点击穿透的圆环光标让用户看见它在点哪。

- 输入走 Win32 `PostMessage` 直投窗口（`WM_LBUTTONDOWN/UP`、`WM_KEYDOWN/WM_CHAR`）：系统光标与前台窗口完全不动，用户和 agent 可以同时用一台机器。
- 光标是 per-pixel alpha 的分层窗口（`WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOPMOST|WS_EX_NOACTIVATE`），点击穿透、不出现在截图里（DWM 限制）。
- 纯 Python 3.9+，只有 Pillow 一个可选依赖；不需要管理员权限，不需要 `danger-full-access`。

### 为什么有用

现有方案要么 `SendInput` 抢鼠标，要么需要提权。而 DSH 默认的低完整性令牌下 `SendInput`/`SetCursorPos` 会**返回成功但静默失效**（实测 5/5 无响应），`PostMessage` 不受影响。

### 已验证

- 非前台 WinForms 窗口的 EDIT 控件：18 字符 + 回车逐字到达（日志逐字回读）
- 客户端坐标点击命中标签，`GetCursorPos` 前后一致
- `WindowFromPoint` 在光标位置返回下层窗口 → 点击穿透成立

### 安装

技能 = 含 `SKILL.md` 的目录：

```powershell
git clone https://github.com/<user>/dsh-skill-ai-desktop
Copy-Item -Recurse dsh-skill-ai-desktop\skills\ai-desktop "$env:USERPROFILE\.dsh\skills\"
# 或 .\install.ps1 -Scope workspace
```

新开会话后技能可见。

### 仓库

https://github.com/<user>/dsh-skill-ai-desktop
```

## 目录条目（按该仓库列表的现有格式追加一条）

```json
{
  "name": "ai-desktop",
  "category": "skill",
  "description": "AI 专属虚拟键鼠：PostMessage 定向点击/打字，不抢系统光标与前台窗口；外加点击穿透的圆环光标，让用户看见 AI 点在哪。",
  "repository": "https://github.com/<user>/dsh-skill-ai-desktop",
  "author": "lixinyu",
  "tags": ["skill", "windows", "automation", "ui-automation", "accessibility"],
  "install": {
    "type": "skill-copy",
    "path": "skills/ai-desktop",
    "docs": "https://github.com/<user>/dsh-skill-ai-desktop#安装"
  }
}
```

> 说明：本包是**纯技能包**（没有 cordis 插件入口）。若列表要求“可 `dsh plugin add` 的安装单元”，需要再补一个 `package.json` + `cordis.patch.yml` 壳；先把技能本体上架，壳可以后加。

## 提交前检查

- [ ] 仓库 public，README 两种语言都在
- [ ] `install.ps1` 在干净目录跑通（已在 `%TEMP%` 实测：复制 + `python vinput.py list` 正常）
- [ ] 没有把个人路径 / 屏幕截图 / 其他项目文件带进去（`.gitignore` 已排除 `*.png`）
- [ ] License 为 MIT，作者名与 GitHub 账号一致
