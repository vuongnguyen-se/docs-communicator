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

# CDK's built-in helper Lambdas (e.g. S3 auto-delete) create their log groups at runtime,
# so those groups are untagged and survive `cdk destroy`. Near-zero cost, but list them.
$logGroups = aws logs describe-log-groups --profile $AwsProfile --region $Region `
    --log-group-name-prefix "/aws/lambda/CloudDocsAI-" `
    --query "logGroups[].logGroupName" --output text

if ([string]::IsNullOrWhiteSpace($stacks) -and [string]::IsNullOrWhiteSpace($tagged)) {
    Write-Host "Teardown check passed: no CloudDocsAI stacks or tagged resources in $Region." -ForegroundColor Green
    if ($logGroups) {
        Write-Host "Leftover helper log groups (safe to delete):`n$($logGroups -replace '\s+', "`n")" -ForegroundColor Yellow
        Write-Host "Delete with: aws logs delete-log-group --log-group-name <name> --profile $AwsProfile --region $Region"
    }
    exit 0
}

Write-Host "Teardown check found leftovers:" -ForegroundColor Red
if ($stacks) { Write-Host "Stacks:`n$stacks" }
if ($tagged) { Write-Host "Tagged resources:`n$($tagged -replace '\s+', "`n")" }
if ($logGroups) { Write-Host "Helper log groups:`n$($logGroups -replace '\s+', "`n")" }
Write-Host "Note: the tagging index can lag a few minutes after deletion; re-run before deleting anything by hand."
exit 1
