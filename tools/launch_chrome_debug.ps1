# Launches a SEPARATE debug Chrome window side-by-side with normal Chrome.
# No need to close existing Chrome: this uses its own profile folder
# (browser_profile/chrome-debug) with --remote-debugging-port=9222 so the
# worker (BROWSER_MODE=attach) can connect via CDP.
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools/launch_chrome_debug.ps1
# Then log in to Exness in THAT debug window, keep it OPEN, run: py main.py
$ErrorActionPreference = "Stop"
$ChromeCandidates = @(
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$Chrome = $ChromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Chrome) { Write-Error "Google Chrome not found." }
$Port = 9222
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DebugProfile = Join-Path $RepoRoot "browser_profile\chrome-debug"
New-Item -ItemType Directory -Force -Path $DebugProfile | Out-Null
Write-Host "Opening SEPARATE debug Chrome (normal Chrome stays open) ..."
Write-Host "Profile: $DebugProfile"
Write-Host "Log in to Exness in THAT window, keep it OPEN, then run: py main.py"
Start-Process -FilePath $Chrome -ArgumentList @(
  "--remote-debugging-port=$Port",
  "--remote-debugging-address=127.0.0.1",
  "--remote-allow-origins=*",
  "--user-data-dir=$DebugProfile",
  "https://my.exness.com/pa/trading/accounts"
)
