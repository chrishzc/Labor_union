<#
File: configure_local_admin_no_auth.ps1
Description: 將本機開發環境設為管理端免登入並保留 dry-run preflight。
#>
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
    ACCESS_CONTROL_PROFILE = "local_bypass"
}

$existing = @()
if (Test-Path -LiteralPath $envFile) {
    $existing = Get-Content -LiteralPath $envFile
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

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$temporaryEnvFile = Join-Path $root (".env.tmp." + [guid]::NewGuid().ToString("N"))
$backupEnvFile = Join-Path $root (".env.backup." + [guid]::NewGuid().ToString("N"))
$envContent = [string]::Join([Environment]::NewLine, [string[]]$next) + [Environment]::NewLine
try {
    [System.IO.File]::WriteAllText($temporaryEnvFile, $envContent, $utf8NoBom)
    if (Test-Path -LiteralPath $envFile) {
        [System.IO.File]::Replace($temporaryEnvFile, $envFile, $backupEnvFile)
    }
    else {
        [System.IO.File]::Move($temporaryEnvFile, $envFile)
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryEnvFile) {
        Remove-Item -LiteralPath $temporaryEnvFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $backupEnvFile) {
        Remove-Item -LiteralPath $backupEnvFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "[OK] .env updated:"
Write-Host "APP_ENV=$($desired['APP_ENV'])"
Write-Host "ENABLE_ADMIN_AUTH=$($desired['ENABLE_ADMIN_AUTH'])"
Write-Host "ACCESS_CONTROL_PROFILE=$($desired['ACCESS_CONTROL_PROFILE'])"
