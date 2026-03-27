[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "Enter Teddy's OpenAI API key. It will be stored in your Windows user environment as OPENAI_API_KEY."
$secureKey = Read-Host -AsSecureString "OpenAI API key"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($plainKey)) {
    throw "No API key was entered."
}

[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $plainKey, "User")
$env:OPENAI_API_KEY = $plainKey

Write-Host "Saved OPENAI_API_KEY to your user environment."
Write-Host "New PowerShell windows will pick it up automatically."
