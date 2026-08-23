<#
File: run_schemathesis_disposable_get.ps1
Description: 在明確 lu_test 資料庫啟動暫時 API，依 OpenAPI 自動驗證全部 GET 契約並確實清理程序。
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern("^lu_test_[a-z0-9_]+$")]
    [string]$DisposableDatabase,

    [Parameter()]
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,

    [Parameter()]
    [ValidateRange(1, 20)]
    [int]$MaxExamples = 1,

    [Parameter()]
    [ValidateRange(1, 200)]
    [int]$MaxFailures = 25,

    [Parameter()]
    [ValidateRange(1, 60)]
    [int]$RequestTimeoutSeconds = 5,

    [Parameter()]
    [ValidateRange(15, 180)]
    [int]$StartupTimeoutSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$workflowStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

$projectRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..")
)
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$schemathesisPath = Join-Path $projectRoot ".venv\Scripts\schemathesis.exe"
$healthRunner = Join-Path $PSScriptRoot "run_schemathesis_health.ps1"
$openApiInspector = Join-Path $PSScriptRoot "inspect_local_openapi.py"
$failureFilter = Join-Path $PSScriptRoot "filter_schemathesis_failures.py"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "找不到專案 .venv Python：$pythonPath"
}
if (-not (Test-Path -LiteralPath $schemathesisPath -PathType Leaf)) {
    throw "找不到專案 .venv Schemathesis：$schemathesisPath"
}
if (-not (Test-Path -LiteralPath $healthRunner -PathType Leaf)) {
    throw "找不到 health gate runner：$healthRunner"
}
if (-not (Test-Path -LiteralPath $openApiInspector -PathType Leaf)) {
    throw "找不到 OpenAPI inspector：$openApiInspector"
}
if (-not (Test-Path -LiteralPath $failureFilter -PathType Leaf)) {
    throw "找不到 Schemathesis failure filter：$failureFilter"
}
$portProbe = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback,
    $Port
)
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
    $originalEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable(
        $entry.Key,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        $entry.Key,
        $entry.Value,
        "Process"
    )
}

$baseUrl = "http://127.0.0.1:$Port"
$schemaUrl = "$baseUrl/openapi.json"
$runIdentity = (
    (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") +
    "_" +
    [guid]::NewGuid().ToString("N").Substring(0, 8)
)
$runDirectory = Join-Path $projectRoot "scratch\schemathesis\$runIdentity"
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$rawReportPath = Join-Path $runDirectory "raw.ndjson"
$agentFailuresPath = Join-Path $runDirectory "unique_failures.ndjson"
$summaryPath = Join-Path $runDirectory "summary.json"
$apiProcess = $null
$schemathesisExitCode = 1
$apiReadyElapsedMilliseconds = 0
$schemathesisElapsedMilliseconds = 0
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

    & $healthRunner `
        -BaseUrl $baseUrl `
        -MaxExamples 1 `
        -RequestTimeoutSeconds $RequestTimeoutSeconds 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Health contract gate 失敗，停止擴大測試。"
    }

    & $pythonPath $openApiInspector `
        --schema-url $schemaUrl `
        --timeout-seconds 30 `
        --count-method get
    if ($LASTEXITCODE -ne 0) {
        throw "OpenAPI GET inventory preflight 失敗。"
    }

    $checks = @(
        "not_a_server_error",
        "status_code_conformance",
        "content_type_conformance",
        "response_schema_conformance"
    ) -join ","
    $schemathesisArguments = @(
        "run",
        $schemaUrl,
        "--url", $baseUrl,
        "--include-method", "GET",
        "--checks", $checks,
        "--phases", "examples,fuzzing",
        "--mode", "positive",
        "--max-examples", $MaxExamples.ToString(),
        "--workers", "1",
        "--max-failures", $MaxFailures.ToString(),
        "--request-timeout", $RequestTimeoutSeconds.ToString(),
        "--request-retries", "0",
        "--max-redirects", "0",
        "--rate-limit", "20/s",
        "--wait-for-schema", "30",
        "--generation-deterministic",
        "--report", "ndjson",
        "--report-ndjson-path", $rawReportPath,
        "--output-sanitize", "true",
        "--no-color"
    )
    $schemathesisStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    & $schemathesisPath @schemathesisArguments 2>&1 | Out-Null
    $schemathesisStopwatch.Stop()
    $schemathesisElapsedMilliseconds = $schemathesisStopwatch.ElapsedMilliseconds
    $schemathesisExitCode = $LASTEXITCODE

    if (-not (Test-Path -LiteralPath $rawReportPath -PathType Leaf)) {
        throw "Schemathesis 未產生 raw NDJSON report。"
    }
    & $pythonPath $failureFilter `
        --input $rawReportPath `
        --output $agentFailuresPath `
        --summary $summaryPath
    if ($LASTEXITCODE -ne 0) {
        throw "Schemathesis failure filter 失敗；拒絕產生 Agent 輸入。"
    }
    $workflowStopwatch.Stop()
    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    $summary | Add-Member -NotePropertyName "workflow_timing" -NotePropertyValue ([ordered]@{
        "api_readiness_milliseconds" = $apiReadyElapsedMilliseconds
        "schemathesis_milliseconds" = $schemathesisElapsedMilliseconds
        "total_through_filter_milliseconds" = $workflowStopwatch.ElapsedMilliseconds
    })
    $summaryTemporaryPath = "$summaryPath.tmp"
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryTemporaryPath -Encoding utf8
    Move-Item -LiteralPath $summaryTemporaryPath -Destination $summaryPath -Force
    Remove-Item -LiteralPath $rawReportPath -Force
    Write-Output "AGENT_FAILURES_PATH=$agentFailuresPath"
    Write-Output "SCHEMATHESIS_SUMMARY_PATH=$summaryPath"
}
finally {
    if ($null -ne $apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
        $apiProcess.WaitForExit()
    }
    foreach ($entry in $originalEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $entry.Key,
            $entry.Value,
            "Process"
        )
    }
    if (Test-Path -LiteralPath $rawReportPath -PathType Leaf) {
        Remove-Item -LiteralPath $rawReportPath -Force
    }
}

exit $schemathesisExitCode
