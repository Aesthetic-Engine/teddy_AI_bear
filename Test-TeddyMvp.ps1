[CmdletBinding()]
param(
    [switch]$PrintOnly,
    [switch]$EnableMouth
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$params = @{
    Once = $true
    Text = "Good evening Teddy. Please greet the user in two short sentences."
}

if ($PrintOnly) {
    $params.PrintOnly = $true
}
if ($EnableMouth) {
    $params.EnableMouth = $true
}

& (Join-Path $RepoRoot "Start-Teddy.ps1") @params
