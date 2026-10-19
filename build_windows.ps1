# Build dist\DivyInvestorPro.exe (single file) on Windows.
# Usage, from the project folder in PowerShell:
#   py -3.13 -m venv .venv
#   .venv\Scripts\pip install -r requirements.txt pillow
#   .\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> Tests"
& $py -m unittest discover -s tests -q
if ($LASTEXITCODE) { exit $LASTEXITCODE }

Write-Host "==> Icon"
& $py tools\make_icon.py build\DivyInvestorPro.png
if ($LASTEXITCODE) { exit $LASTEXITCODE }

Write-Host "==> Executable"
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --log-level WARN `
    --name DivyInvestorPro `
    --icon build\DivyInvestorPro.png `
    run.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$exe = Get-Item dist\DivyInvestorPro.exe
Write-Host ("==> Done: {0} ({1:N0} MB)" -f $exe.FullName, ($exe.Length / 1MB))
