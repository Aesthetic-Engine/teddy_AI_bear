[CmdletBinding()]
param(
    [string]$Name = "",
    [string]$CallName = "",
    [string]$Pronouns = "",
    [string]$Timezone = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$userFile = Join-Path $RepoRoot "workspace" "USER.md"

if (-not (Test-Path $userFile)) {
    throw "USER.md not found at '$userFile'."
}

if (-not $Name) {
    $Name = Read-Host "Your name"
}
if (-not $CallName) {
    $CallName = Read-Host "What Teddy should call you (press Enter to use your name)"
    if (-not $CallName) {
        $CallName = $Name
    }
}
if (-not $Pronouns) {
    $Pronouns = Read-Host "Pronouns (optional)"
}
if (-not $Timezone) {
    $Timezone = Read-Host "Timezone (optional)"
}

if ([string]::IsNullOrWhiteSpace($Name)) {
    throw "A name is required."
}

$pronounsValue = if ([string]::IsNullOrWhiteSpace($Pronouns)) { "(optional)" } else { $Pronouns.Trim() }
$timezoneValue = if ([string]::IsNullOrWhiteSpace($Timezone)) { "(set this after the host-side runtime is fully configured)" } else { $Timezone.Trim() }

$content = @"
# USER.md - About Your Human

- Name:
$($Name.Trim())

- What to call them:
$($CallName.Trim())

- Pronouns:
$pronounsValue

- Timezone:
$timezoneValue

- Notes:
The user is building or configuring Project Teddy, an embodied local AI companion with a voice-first interface and a plush-bear form factor.

## Context

The user prefers direct, practical help over long explanations.

They like small, focused changes and want systems that are explicit, boring in the good way, and dependable.

They value strong local control, clean architecture, smooth dev flows, and setups that do not surprise them.

They are interested in real isolation and want Teddy, its dependencies, and any local models to stay contained rather than casually reaching into the rest of the machine.

When helping the user:
- be proactive
- do not over-explain unless asked
- flag scope creep or technical debt plainly
- prefer concrete next steps over abstract discussion
"@

Set-Content -Path $userFile -Value $content -Encoding UTF8
Write-Host "Updated workspace/USER.md"
Write-Host "Teddy will now use '$CallName' as the preferred spoken name."
