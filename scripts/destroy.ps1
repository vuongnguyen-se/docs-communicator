# Tear down the CloudDocs AI dev environment, then verify nothing tagged is left (D-002).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\destroy.ps1 [-AwsProfile clouddocs-dev] [-Force]
param(
    [string]$AwsProfile = "clouddocs-dev",
    # Skip cdk's "Are you sure?" prompt, for non-interactive runs (no terminal to answer).
    [switch]$Force
)
$ErrorActionPreference = "Stop"

$infra = Join-Path $PSScriptRoot "..\infrastructure"
Push-Location $infra
try {
    . (Join-Path $PSScriptRoot "use-infra-venv.ps1")
    $extra = @()
    if ($Force) { $extra += "--force" }
    cdk destroy --profile $AwsProfile @extra   # asks for confirmation unless -Force
    if ($LASTEXITCODE -ne 0) { throw "cdk destroy failed" }
    Remove-Item -ErrorAction SilentlyContinue cdk-outputs.json
}
finally { Pop-Location }

# -Cleanup removes untagged log groups that Lambdas recreate during stack deletion.
& (Join-Path $PSScriptRoot "check-teardown.ps1") -AwsProfile $AwsProfile -Cleanup
