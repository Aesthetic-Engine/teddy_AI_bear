[CmdletBinding()]
param(
    [string]$ComPort = "COM7",
    [int]$Baud = 9600,
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scriptPath = Join-Path $RepoRoot "bridge" "teddy_mouth_bridge.py"

if (-not (Test-Path $scriptPath)) {
    throw "Bridge script not found at '$scriptPath'."
}

python $scriptPath --com $ComPort --baud $Baud serve --host $BindHost --port $Port
