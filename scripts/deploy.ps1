# Deploy the Clouddocs dev environment. Costs money while it exists: run destroy.ps1 when done.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 [-AwsProfile clouddocs-dev] [-AlarmEmail you@example.com] [-RequireApproval never]
param(
    [string]$AwsProfile = "clouddocs-dev",
    # Optional: email for CloudWatch alarms (P5-03). Passed at deploy time, never stored in the repo.
    [string]$AlarmEmail = "",
    # 'broadening' (default) stops for confirmation whenever IAM permissions or security groups widen.
    # 'never' is for non-interactive runs (no terminal to answer), after the IAM review (docs/iam-review.md).
    [ValidateSet("broadening", "never")][string]$RequireApproval = "broadening"
)
$ErrorActionPreference = "Stop"

$infra = Join-Path $PSScriptRoot "..\infrastructure"
Push-Location $infra
try {
    . (Join-Path $PSScriptRoot "use-infra-venv.ps1")
    aws sts get-caller-identity --profile $AwsProfile --query Arn --output text | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Not logged in. Run: aws sso login --profile $AwsProfile" }

    $extra = @()
    if ($AlarmEmail) { $extra += @("-c", "alarmEmail=$AlarmEmail") }
    cdk deploy --profile $AwsProfile --require-approval $RequireApproval --outputs-file cdk-outputs.json @extra
    if ($LASTEXITCODE -ne 0) { throw "cdk deploy failed" }
    if ($AlarmEmail) { Write-Host "Confirm the SNS subscription email AWS just sent to $AlarmEmail, or alarms won't reach you." -ForegroundColor Yellow }
    Write-Host "`nOutputs saved to infrastructure\cdk-outputs.json (git-ignored)."
    Write-Host "REMINDER: run scripts\destroy.ps1 when you finish this session." -ForegroundColor Yellow
}
finally { Pop-Location }
