#Requires -Version 5.1
<#
  Install the ai-desktop skill for DeepSeek Harness.

  .\install.ps1                # workspace scope (./.dsh/skills)
  .\install.ps1 -Scope profile # global (~/.dsh/skills)
#>
param(
    [ValidateSet('workspace', 'profile')]
    [string]$Scope = 'workspace'
)

$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot 'skills\ai-desktop'
if (-not (Test-Path $src)) { throw "skill source not found: $src" }

# 1) python sanity check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Warning 'python not found in PATH — the skill needs Python 3.9+ to run.'
} else {
    $ver = & $py.Source -c "import sys;print('.'.join(map(str,sys.version_info[:2])))"
    Write-Host "python $ver  ($($py.Source))"
}

# 2) copy into the skills dir
$destRoot = if ($Scope -eq 'profile') { Join-Path $env:USERPROFILE '.dsh\skills' } else { Join-Path (Get-Location) '.dsh\skills' }
$dest = Join-Path $destRoot 'ai-desktop'
New-Item -ItemType Directory -Force -Path $destRoot | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse $src $dest

Write-Host "installed -> $dest"

# 3) smoke test (non-blocking: only lists windows)
$vinput = Join-Path $dest 'scripts\vinput.py'
if ($py -and (Test-Path $vinput)) {
    Write-Host "`nsmoke test: python `"$vinput`" list"
    try { & $py.Source $vinput list | Select-Object -First 5 } catch { Write-Warning "list failed: $_" }
}

Write-Host @"

Done. Start a NEW DSH session (skills are scanned at session start), then try:
  python "$vinput" cursor 900 300 10 96
"@
