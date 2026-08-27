# ok-jump test runner (ASCII only: PS 5.1 reads no-BOM files as ANSI)
# Auto-detects the .venv interpreter and runs pytest without shell activation.
# Usage: .\run_tests.ps1 [-VerboseOutput]

param(
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $scriptDir

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $baselinePython = Join-Path $scriptDir ".venv-baseline\Scripts\python.exe"
    if (Test-Path $baselinePython) {
        $venvPython = $baselinePython
        Write-Host "Using baseline venv: $venvPython" -ForegroundColor Yellow
    } else {
        $venvPython = "python"
        Write-Host ".venv not found, falling back to system python" -ForegroundColor Yellow
    }
}

Write-Host "===== ok-jump test suite =====" -ForegroundColor Cyan
Write-Host "Interpreter: $venvPython"
& $venvPython -c "import sys; print(f'Python {sys.version.split()[0]} @ {sys.executable}')"
& $venvPython -c "import importlib.metadata as md; print('ok-script', md.version('ok-script'))"

# Ensure pytest is available
& $venvPython -m pytest --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pytest missing, installing dev dependency..." -ForegroundColor Yellow
    & $venvPython -m pip install pytest
}

if ($VerboseOutput) {
    & $venvPython -m pytest tests/ --tb=long -v
} else {
    & $venvPython -m pytest tests/ --tb=short -q
}
exit $LASTEXITCODE
