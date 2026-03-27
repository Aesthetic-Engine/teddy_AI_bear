[CmdletBinding()]
param(
    [string]$Text = "Hi this is Teddy. Do you like this voice?",
    [string]$ModelsDir = "G:\F4SE\Plugins\MantellaSoftware\piper\models\fallout4\low",
    [double]$PauseSeconds = 0.75
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

python -m runtime.voice_bakeoff --text $Text --models-dir $ModelsDir --pause-seconds $PauseSeconds
