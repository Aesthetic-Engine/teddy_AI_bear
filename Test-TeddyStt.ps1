[CmdletBinding()]
param(
    [string]$Text = "Hello Teddy. This is a speech recognition test."
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$encodedText = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
@" 
import base64
from runtime.tts_client import synthesize_to_wav
text = base64.b64decode("$encodedText").decode("utf-8")
path = synthesize_to_wav(text)
print(path)
"@ | python - | ForEach-Object {
    $wavPath = $_.Trim()
    if ($wavPath) {
        $bytes = [System.IO.File]::ReadAllBytes($wavPath)
        $response = Invoke-WebRequest -UseBasicParsing `
            -Method Post `
            -Uri "http://127.0.0.1:8000/v1/transcribe" `
            -ContentType "audio/wav" `
            -Body $bytes
        Write-Host $response.Content
    }
}
