# Lists anything still tagged Project=CloudDocsAI, plus any leftover CloudDocsAI stack. Read-only.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\check-teardown.ps1 [-AwsProfile clouddocs-dev]
param(
    [string]$AwsProfile = "clouddocs-dev",
    [string]$Region = "ap-southeast-1"
)

$stacks = aws cloudformation list-stacks --profile $AwsProfile --region $Region `
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE ROLLBACK_COMPLETE DELETE_FAILED `
    --query "StackSummaries[?starts_with(StackName, 'CloudDocsAI')].[StackName,StackStatus]" --output text

$tagged = aws resourcegroupstaggingapi get-resources --profile $AwsProfile --region $Region `
    --tag-filters Key=Project,Values=CloudDocsAI `
    --query "ResourceTagMappingList[].ResourceARN" --output text

if ([string]::IsNullOrWhiteSpace($stacks) -and [string]::IsNullOrWhiteSpace($tagged)) {
    Write-Host "Teardown check passed: no CloudDocsAI stacks or tagged resources in $Region." -ForegroundColor Green
    exit 0
}

Write-Host "Teardown check found leftovers:" -ForegroundColor Red
if ($stacks) { Write-Host "Stacks:`n$stacks" }
if ($tagged) { Write-Host "Tagged resources:`n$($tagged -replace '\s+', "`n")" }
Write-Host "Note: the tagging index can lag a few minutes after deletion; re-run before deleting anything by hand."
exit 1
