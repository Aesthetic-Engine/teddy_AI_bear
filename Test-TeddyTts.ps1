[CmdletBinding()]
param(
    [string]$Text = "Hello. Teddy's offline Piper voice is online."
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$body = @{
    input = $Text
    model = "en_US-ryan-high"
    response_format = "wav"
} | ConvertTo-Json

$response = Invoke-WebRequest -UseBasicParsing `
    -Method Post `
    -Uri "http://127.0.0.1:5000/v1/audio/speech" `
    -ContentType "application/json" `
    -Body $body

$path = Join-Path $RepoRoot "tmp" "teddy-tts-test.wav"
[System.IO.File]::WriteAllBytes($path, $response.Content)
Write-Host $path
