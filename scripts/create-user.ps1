# Create an app user (self sign-up is disabled, D-004). Cognito emails a temporary password;
# the user sets a new one on first login.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\create-user.ps1 -Email you@example.com [-AwsProfile clouddocs-dev]
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [string]$AwsProfile = "clouddocs-dev"
)
$ErrorActionPreference = "Stop"

$outputsFile = Join-Path $PSScriptRoot "..\infrastructure\cdk-outputs.json"
if (-not (Test-Path $outputsFile)) { throw "Deploy first (scripts\deploy.ps1): $outputsFile not found." }
$outputs = (Get-Content $outputsFile -Raw | ConvertFrom-Json).'CloudDocsAI-dev'

aws cognito-idp admin-create-user --profile $AwsProfile --region $outputs.Region `
    --user-pool-id $outputs.UserPoolId `
    --username $Email `
    --user-attributes Name=email,Value=$Email Name=email_verified,Value=true `
    --desired-delivery-mediums EMAIL `
    --query "User.UserStatus" --output text
if ($LASTEXITCODE -ne 0) { throw "admin-create-user failed" }
Write-Host "User created. Check $Email for the temporary password."
