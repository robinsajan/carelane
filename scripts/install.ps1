param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
  if (-not (Test-Path -LiteralPath "backend/.venv/Scripts/python.exe")) {
    & $Python -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
  }
  & ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
  if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
  Push-Location frontend
  try {
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
  } finally { Pop-Location }
  & ./backend/.venv/Scripts/python.exe -m backend.manage init
  if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }
  Write-Host "Installation complete. Run scripts/start.ps1 from this project."
} finally { Pop-Location }
