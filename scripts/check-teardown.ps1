# Verifies nothing from CloudDocs AI is left after `cdk destroy` (D-002). Read-only unless -Cleanup.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\check-teardown.ps1 [-AwsProfile clouddocs-dev] [-Cleanup]
#   -Cleanup  deletes leftover CloudDocsAI log groups (the only leftovers expected after a destroy).
param(
    [string]$AwsProfile = "clouddocs-dev",
    [string]$Region = "ap-southeast-1",
    [switch]$Cleanup
)

$stacks = aws cloudformation list-stacks --profile $AwsProfile --region $Region `
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE ROLLBACK_COMPLETE DELETE_FAILED DELETE_IN_PROGRESS `
    --query "StackSummaries[?starts_with(StackName, 'CloudDocsAI')].[StackName,StackStatus]" --output text

$tagged = aws resourcegroupstaggingapi get-resources --profile $AwsProfile --region $Region `
    --tag-filters Key=Project,Values=CloudDocsAI `
    --query "ResourceTagMappingList[].ResourceARN" --output text

# Log groups created at runtime by Lambdas (CDK helper functions, or a function logging during
# stack deletion) are untagged and can survive `cdk destroy`. Match any name containing CloudDocsAI.
$logGroups = aws logs describe-log-groups --profile $AwsProfile --region $Region `
    --log-group-name-pattern "CloudDocsAI" --query "logGroups[].logGroupName" --output text

if ($Cleanup -and $logGroups) {
    foreach ($g in ($logGroups -split '\s+' | Where-Object { $_ })) {
        aws logs delete-log-group --log-group-name $g --profile $AwsProfile --region $Region
        if ($LASTEXITCODE -eq 0) { Write-Host "Deleted log group $g" }
    }
    $logGroups = aws logs describe-log-groups --profile $AwsProfile --region $Region `
        --log-group-name-pattern "CloudDocsAI" --query "logGroups[].logGroupName" --output text
}

$ok = $true
if ($stacks) {
    $ok = $false
    Write-Host "Stacks still present:`n$stacks" -ForegroundColor Red
}
if ($tagged) {
    if ($stacks) {
        $ok = $false
        Write-Host "Tagged resources:`n$($tagged -replace '\s+', "`n")" -ForegroundColor Red
    } else {
        # No stack left: these ARNs are almost always a stale tagging index (it lags up to ~15 min).
        Write-Host "Tagging index still lists (likely stale, stack is gone):`n$($tagged -replace '\s+', "`n")" -ForegroundColor Yellow
        Write-Host "Re-run this check in ~15 minutes to confirm."
    }
}
if ($logGroups) {
    $ok = $false
    Write-Host "Leftover log groups:`n$($logGroups -replace '\s+', "`n")" -ForegroundColor Red
    Write-Host "Re-run with -Cleanup to delete them."
}

if ($ok) {
    Write-Host "Teardown check passed: no CloudDocsAI stacks or log groups in $Region." -ForegroundColor Green
    exit 0
}
exit 1
