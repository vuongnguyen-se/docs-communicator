# Deploy the CloudDocs AI dev environment. Costs money while it exists: run destroy.ps1 when done.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 [-AwsProfile clouddocs-dev]
param([string]$AwsProfile = "clouddocs-dev")
$ErrorActionPreference = "Stop"

$infra = Join-Path $PSScriptRoot "..\infrastructure"
Push-Location $infra
try {
    & .\.venv\Scripts\Activate.ps1
    aws sts get-caller-identity --profile $AwsProfile --query Arn --output text | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Not logged in. Run: aws sso login --profile $AwsProfile" }

    # 'broadening' asks for confirmation whenever IAM permissions or security groups widen.
    cdk deploy --profile $AwsProfile --require-approval broadening --outputs-file cdk-outputs.json
    if ($LASTEXITCODE -ne 0) { throw "cdk deploy failed" }
    Write-Host "`nOutputs saved to infrastructure\cdk-outputs.json (git-ignored)."
    Write-Host "REMINDER: run scripts\destroy.ps1 when you finish this session." -ForegroundColor Yellow
}
finally { Pop-Location }
