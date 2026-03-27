[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

if ($Restart) {
    $processId = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess
    if ($processId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

if (-not $Restart) {
    try {
        $health = Invoke-WebRequest -UseBasicParsing "http://$BindHost`:$Port/health" -TimeoutSec 3
        if ($health.StatusCode -eq 200) {
            Write-Host "Teddy TTS service is already running."
            return
        }
    }
    catch {
    }
}

python -m uvicorn runtime.piper_tts_server:app --host $BindHost --port $Port
