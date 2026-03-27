[CmdletBinding()]
param(
    [ValidateRange(4, 12)]
    [int]$Angle = 4,

    [string]$ComPort = "COM7",
    [int]$Baud = 9600
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scriptPath = Join-Path $RepoRoot "bridge" "teddy_mouth_bridge.py"

if (-not (Test-Path $scriptPath)) {
    throw "Bridge script not found at '$scriptPath'."
}

python $scriptPath --com $ComPort --baud $Baud angle $Angle
