param([switch]$Lan, [switch]$Demo, [int]$Port = 3000, [int]$ApiPort = 8000)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot "backend/.venv/Scripts/python.exe"
$nextScript = Join-Path $projectRoot "frontend/node_modules/next/dist/bin/next"
if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Run scripts/install.ps1 first." }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend/.next/BUILD_ID'))) { throw "Run npm.cmd run build in frontend first." }
$previousDatabase = $env:OPD_DATABASE
$previousLocalDb = $env:local_db
$previousApiUrl = $env:API_URL
$previousTelemetry = $env:NEXT_TELEMETRY_DISABLED
$bindAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
try {
  $env:NEXT_TELEMETRY_DISABLED = '1'
  $env:API_URL = "http://127.0.0.1:$ApiPort"
  if ($Demo) {
    $env:local_db = 'True'
    $env:OPD_DATABASE = Join-Path $projectRoot 'backend/data/preview.sqlite3'
    if (-not (Test-Path -LiteralPath $env:OPD_DATABASE)) { throw "Create fictional data with: backend/.venv/Scripts/python.exe -m backend.seed_demo" }
  } elseif (-not $env:OPD_DATABASE) {
    $env:OPD_DATABASE = Join-Path $projectRoot 'backend/data/opd.sqlite3'
  }
  Push-Location $projectRoot
  try {
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',"$ApiPort",'--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    try {
      Start-Sleep -Milliseconds 800
      if ($apiProcess.HasExited) { throw "FastAPI could not start. Check whether API port $ApiPort is already in use." }
      Write-Host "Hospital OPD: http://localhost:$Port"
      Write-Host "Keep this terminal running. Ctrl+C stops both services."
      if ($Lan) { Write-Host "LAN access enabled on frontend port $Port. Configure local HTTPS and firewall rules before using real patient data." }
      & node $nextScript start (Join-Path $projectRoot 'frontend') --hostname $bindAddress --port $Port
      if ($LASTEXITCODE -ne 0) { throw "The frontend exited with an error. Check whether port $Port is in use." }
    } finally {
      if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id }
    }
  } finally { Pop-Location }
} finally {
  $env:OPD_DATABASE = $previousDatabase
  $env:local_db = $previousLocalDb
  $env:API_URL = $previousApiUrl
  $env:NEXT_TELEMETRY_DISABLED = $previousTelemetry
}
