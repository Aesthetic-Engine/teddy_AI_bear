[CmdletBinding()]
param(
    [switch]$Once,
    [string]$Text,
    [switch]$PrintOnly,
    [switch]$EnableMouth,
    [switch]$AutoListen,
    [Alias("Profile")]
    [switch]$ShowProfile
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$storedKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
if (-not $storedKey) {
    $storedKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Machine")
}
if ($storedKey) {
    $env:OPENAI_API_KEY = $storedKey
}

if ($ShowProfile) {
    $env:TEDDY_PROFILE_TURNS = "1"
    $env:TEDDY_MOUTH_TRACE = "1"
} else {
    $env:TEDDY_PROFILE_TURNS = "0"
    $env:TEDDY_MOUTH_TRACE = "0"
}

if ($EnableMouth) {
    $env:TEDDY_ENABLE_MOUTH = "1"
} else {
    $env:TEDDY_ENABLE_MOUTH = "0"
}

function Test-LocalService {
    param(
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Start-LocalServiceIfNeeded {
    param(
        [string]$Name,
        [string]$HealthUrl,
        [string]$ScriptPath
    )

    if (Test-LocalService -Url $HealthUrl) {
        return
    }

    Start-Process powershell `
        -WindowStyle Hidden `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $ScriptPath
        ) | Out-Null

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-LocalService -Url $HealthUrl) {
            return
        }
    }

    throw "$Name failed to start."
}

Start-LocalServiceIfNeeded `
    -Name "Teddy TTS service" `
    -HealthUrl "http://127.0.0.1:5000/health" `
    -ScriptPath (Join-Path $RepoRoot "Start-TeddyTts.ps1")

if ($AutoListen) {
    Start-LocalServiceIfNeeded `
        -Name "Teddy STT service" `
        -HealthUrl "http://127.0.0.1:8000/health" `
        -ScriptPath (Join-Path $RepoRoot "Start-TeddyStt.ps1")
}

if ($EnableMouth) {
    try {
        Start-LocalServiceIfNeeded `
            -Name "Teddy mouth bridge" `
            -HealthUrl "http://127.0.0.1:8765/health" `
            -ScriptPath (Join-Path $RepoRoot "bridge" "Start-TeddyMouthBridge.ps1")
    }
    catch {
        Write-Warning "Teddy mouth bridge is unavailable. Continuing with voice only."
        $env:TEDDY_ENABLE_MOUTH = "0"
    }
}

$pythonArgs = @("-m", "runtime.teddy_loop")
if ($Once) {
    $pythonArgs += "--once"
}
if ($Text) {
    $pythonArgs += @("--text", $Text)
}
if ($PrintOnly) {
    $pythonArgs += "--print-only"
}
if ($AutoListen) {
    $pythonArgs += "--auto-listen"
}
if ($ShowProfile) {
    $pythonArgs += "--profile"
}

python @pythonArgs
