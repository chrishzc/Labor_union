<#
File: run_hurl_matching_recommend_staff.ps1
Description: 在 lu_test 暫時 API 執行月嫂推薦 Hurl regression，僅保存狀態與耗時。
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern("^lu_test_[a-z0-9_]+$")]
    [string]$DisposableDatabase,

    [Parameter()]
    [ValidateRange(1024, 65535)]
    [int]$Port = 8766,

    [Parameter()]
    [ValidateRange(15, 180)]
    [int]$StartupTimeoutSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$workflowStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$hurlExecutable = Join-Path $projectRoot ".venv\Tools\hurl\hurl.exe"
$hurlCasePath = Join-Path $projectRoot "tests\hurl\matching_recommend_staff.hurl"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "找不到專案 .venv Python：$pythonPath"
}
if (-not (Test-Path -LiteralPath $hurlExecutable -PathType Leaf)) {
    throw "找不到專案 .venv Hurl：$hurlExecutable"
}
if (-not (Test-Path -LiteralPath $hurlCasePath -PathType Leaf)) {
    throw "找不到 Hurl regression：$hurlCasePath"
}

$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try {
    $portProbe.Start()
}
catch {
    throw "localhost:$Port 已被占用；拒絕連到來源不明的既有服務。"
}
finally {
    $portProbe.Stop()
}

$controlledEnvironment = @{
    "APP_ENV" = "test"
    "ACCESS_CONTROL_PROFILE" = "local_bypass"
    "ENABLE_ADMIN_AUTH" = "false"
    "DB_DATABASE" = $DisposableDatabase
}
$originalEnvironment = @{}
foreach ($entry in $controlledEnvironment.GetEnumerator()) {
    $originalEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, "Process")
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
}

$baseUrl = "http://127.0.0.1:$Port"
$runIdentity = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") + "_" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$runDirectory = Join-Path $projectRoot "scratch\hurl\$runIdentity"
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$receiptPath = Join-Path $runDirectory "regression_receipt.json"
$apiProcess = $null
$hurlExitCode = 1
$apiReadyElapsedMilliseconds = 0
try {
    $apiProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "api.main:app",
            "--host", "127.0.0.1",
            "--port", $Port.ToString(),
            "--log-level", "warning"
        ) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru

    $apiReady = $false
    for ($attempt = 0; $attempt -lt ($StartupTimeoutSeconds * 2); $attempt++) {
        if ($apiProcess.HasExited) {
            throw "FastAPI 在 readiness gate 前異常結束，exit code $($apiProcess.ExitCode)。"
        }
        try {
            $healthResponse = Invoke-WebRequest `
                -Uri "$baseUrl/health" `
                -Method Get `
                -MaximumRedirection 0 `
                -TimeoutSec 1 `
                -UseBasicParsing
            if ($healthResponse.StatusCode -eq 200) {
                $apiReady = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $apiReady) {
        throw "FastAPI 未在 $StartupTimeoutSeconds 秒內通過 readiness gate。"
    }
    $apiReadyElapsedMilliseconds = $workflowStopwatch.ElapsedMilliseconds

    & $hurlExecutable `
        --test `
        --jobs 1 `
        --no-output `
        --variable "base_url=$baseUrl" `
        $hurlCasePath
    $hurlExitCode = $LASTEXITCODE
    $workflowStopwatch.Stop()
    $receipt = [ordered]@{
        "schema_version" = 1
        "case" = "matching_recommend_staff"
        "expected_http_status" = 200
        "result" = if ($hurlExitCode -eq 0) { "passed" } else { "failed" }
        "hurl_exit_code" = $hurlExitCode
        "api_readiness_milliseconds" = $apiReadyElapsedMilliseconds
        "total_milliseconds" = $workflowStopwatch.ElapsedMilliseconds
        "response_body_persisted" = $false
    }
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    Write-Output "HURL_RECEIPT_PATH=$receiptPath"
}
finally {
    if ($null -ne $apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
        $apiProcess.WaitForExit()
    }
    foreach ($entry in $originalEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
}

exit $hurlExitCode
