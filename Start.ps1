param([switch]$Rebuild, [ValidateSet('mock','mqtt')][string]$DeviceMode='mock')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$tools='C:\Users\22081\Documents\Codex\tools\visionguard'
$python=Join-Path $tools '.venv\Scripts\python.exe'
if (!(Test-Path $python)) { throw 'Python environment missing. See README.' }
$env:VISIONGUARD_DATA=Join-Path $PSScriptRoot 'data'
$env:YOLO_WEIGHTS=Join-Path $PSScriptRoot 'models\yolo11n.pt'
$env:YOLO_CONFIG_DIR=Join-Path $PSScriptRoot 'data'
$env:DEVICE_MODE=$DeviceMode
New-Item -ItemType Directory -Force -Path $env:VISIONGUARD_DATA | Out-Null
if ($Rebuild -or !(Test-Path 'frontend\dist\index.html')) {
    $env:npm_config_cache=Join-Path $PSScriptRoot '.npm-cache'
    Push-Location frontend
    try {
        npm.cmd ci --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Write-Host 'Open http://127.0.0.1:8000 . Approval token appears below.'
& $python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

