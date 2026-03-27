[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "== Teddy Runtime Validation =="

Write-Host ""
Write-Host "-- Workspace files --"
Get-ChildItem (Join-Path $RepoRoot "workspace") -Force |
    Select-Object Name, Length |
    Format-Table -AutoSize

Write-Host ""
Write-Host "-- Mouth bridge serial test --"
powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "bridge" "Test-TeddyMouthBridge.ps1") -Angle 4
