param(
  [switch]$Resume
)

$ErrorActionPreference = "Stop"
$profileName = "agentic"

Write-Host "Example agent-loop driver"
Write-Host "Profile: $profileName"
if ($Resume) {
  Write-Host "Resume requested"
}

$selfImprove = Join-Path $PSScriptRoot "..\..\self_improve.py"
if (Test-Path $selfImprove) {
  py -3 $selfImprove $PSScriptRoot
}
