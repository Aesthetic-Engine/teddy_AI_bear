[CmdletBinding()]
param(
    [string]$OutputRoot = "grading",
    [switch]$NoJudge,
    [string]$Case = "",
    [ValidateSet("stage1", "stage2", "all")]
    [string]$Suite = "stage1",
    [switch]$IncludeEmbodiment
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$resolvedOutputRoot = Join-Path $RepoRoot $OutputRoot
$argsList = @("-m", "grading.runner", "--output-root", $resolvedOutputRoot, "--suite", $Suite)
if ($NoJudge) {
    $argsList += "--no-judge"
}
if ($Case) {
    $argsList += @("--case", $Case)
}
if ($IncludeEmbodiment) {
    $argsList += "--include-embodiment"
}

python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Teddy grading run failed with exit code $LASTEXITCODE"
}
