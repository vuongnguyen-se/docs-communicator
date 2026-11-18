# Tear down the CloudDocs AI dev environment, then verify nothing tagged is left (D-002).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\destroy.ps1 [-AwsProfile clouddocs-dev]
param([string]$AwsProfile = "clouddocs-dev")
$ErrorActionPreference = "Stop"

$infra = Join-Path $PSScriptRoot "..\infrastructure"
Push-Location $infra
try {
    & .\.venv\Scripts\Activate.ps1
    cdk destroy --profile $AwsProfile   # asks for confirmation
    if ($LASTEXITCODE -ne 0) { throw "cdk destroy failed" }
    Remove-Item -ErrorAction SilentlyContinue cdk-outputs.json
}
finally { Pop-Location }

# -Cleanup removes untagged log groups that Lambdas recreate during stack deletion.
& (Join-Path $PSScriptRoot "check-teardown.ps1") -AwsProfile $AwsProfile -Cleanup
