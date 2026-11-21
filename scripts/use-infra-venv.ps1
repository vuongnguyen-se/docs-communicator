# Activates the infrastructure Python virtual environment for the CDK scripts.
# Convention: infrastructure\.venv (README). infrastructure\venv is also accepted.
# Dot-source it from a script running in the infrastructure folder: . (Join-Path $PSScriptRoot "use-infra-venv.ps1")
$venvName = @(".venv", "venv") | Where-Object { Test-Path ".\$_\Scripts\Activate.ps1" } | Select-Object -First 1
if (-not $venvName) {
    throw "No Python virtual environment in infrastructure\. Create it: python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements-dev.txt"
}
& ".\$venvName\Scripts\Activate.ps1"
