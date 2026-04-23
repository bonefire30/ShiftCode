# 在项目根目录执行: .\scripts\run_backend.ps1
# 需已 conda activate shiftcode
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $env:Path.Contains("Go\bin")) {
  $env:Path = "C:\Program Files\Go\bin;" + $env:Path
}
& python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
