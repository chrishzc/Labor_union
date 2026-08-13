[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptRoot)
$envFile = Join-Path $root ".env"

if ($DryRun) {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Project Python is missing: $python"
    }
    & $python -m scripts.launcher_preflight --profile admin-no-auth
    exit $LASTEXITCODE
}

$desired = [ordered]@{
    APP_ENV = "development"
    ENABLE_ADMIN_AUTH = "false"
}

$existing = @()
if (Test-Path $envFile) {
    $existing = Get-Content -Path $envFile
}

$seen = @{}
$next = @()
foreach ($line in $existing) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
        $key = $matches[1]
        if ($desired.Contains($key)) {
            if (-not $seen.ContainsKey($key)) {
                $next += "$($key)=$($desired[$key])"
                $seen[$key] = $true
            }
            continue
        }
    }
    $next += $line
}

foreach ($key in $desired.Keys) {
    if (-not $seen.ContainsKey($key)) {
        $next += "$($key)=$($desired[$key])"
    }
}

Set-Content -Path $envFile -Value $next -Encoding UTF8

Write-Host "[OK] .env updated:"
Write-Host "APP_ENV=$($desired['APP_ENV'])"
Write-Host "ENABLE_ADMIN_AUTH=$($desired['ENABLE_ADMIN_AUTH'])"
