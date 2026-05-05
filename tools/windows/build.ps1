param(
  [string]$AppName = "ELK-BLEDOM LED Controller",
  [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..\..")

try {
  if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
  }

  .\.venv\Scripts\Activate.ps1

  python -m pip install --upgrade pip
  pip install -r requirements.txt
  pip install -r tools\windows\requirements-build.txt

  Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

  pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "elk-bledom-controller" `
    --add-data "README.md;." `
    main.py

  Write-Host "Built: dist\elk-bledom-controller\elk-bledom-controller.exe"
  Write-Host "Next: run Inno Setup on tools\windows\installer.iss (Version=$Version)"
} finally {
  Pop-Location
}

