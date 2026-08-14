[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GraphifyArguments
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$graphifyExecutable = Join-Path $projectRoot '.venv\Scripts\graphify.exe'

if (-not (Test-Path -LiteralPath $graphifyExecutable -PathType Leaf)) {
    Write-Error 'Project-local Graphify executable is unavailable in .venv.'
    exit 127
}

& $graphifyExecutable @GraphifyArguments
exit $LASTEXITCODE
