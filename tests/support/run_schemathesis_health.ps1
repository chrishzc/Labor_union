<#
File: run_schemathesis_health.ps1
Description: 以 localhost 唯讀 health 契約測試驗證 OpenAPI 回應，不允許 mutation 或遠端目標。
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string]$BaseUrl = "http://127.0.0.1:8000",

    [Parameter()]
    [ValidateRange(1, 100)]
    [int]$MaxExamples = 10,

    [Parameter()]
    [ValidateRange(1, 60)]
    [int]$RequestTimeoutSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $targetUri = [System.Uri]::new($BaseUrl, [System.UriKind]::Absolute)
}
catch {
    throw "BaseUrl 必須是有效的絕對 URL。"
}

if ($targetUri.Scheme -notin @("http", "https")) {
    throw "BaseUrl 只允許 http 或 https。"
}
if (-not $targetUri.IsLoopback) {
    throw "BaseUrl 必須指向 localhost、127.0.0.1 或 ::1。"
}
if ($targetUri.UserInfo -or $targetUri.Query -or $targetUri.Fragment) {
    throw "BaseUrl 不得包含 credential、query 或 fragment。"
}
if ($targetUri.AbsolutePath -ne "/") {
    throw "BaseUrl 不得包含額外 path。"
}

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$schemathesisPath = Join-Path $projectRoot ".venv\Scripts\schemathesis.exe"
$openApiInspector = Join-Path $PSScriptRoot "inspect_local_openapi.py"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "找不到專案 .venv Python：$pythonPath"
}
if (-not (Test-Path -LiteralPath $schemathesisPath -PathType Leaf)) {
    throw "找不到專案 .venv Schemathesis：$schemathesisPath"
}
if (-not (Test-Path -LiteralPath $openApiInspector -PathType Leaf)) {
    throw "找不到 OpenAPI inspector：$openApiInspector"
}
$normalizedBaseUrl = $targetUri.AbsoluteUri.TrimEnd("/")
$schemaUrl = "$normalizedBaseUrl/openapi.json"
$schemaTimeoutSeconds = [System.Math]::Max(15, $RequestTimeoutSeconds)
& $pythonPath $openApiInspector `
    --schema-url $schemaUrl `
    --timeout-seconds $schemaTimeoutSeconds `
    --require-only-get-path "/health"
if ($LASTEXITCODE -ne 0) {
    throw "OpenAPI health safety preflight 失敗。"
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
    "--url", $normalizedBaseUrl,
    "--include-path", "/health",
    "--wait-for-schema", $schemaTimeoutSeconds.ToString(),
    "--checks", $checks,
    "--phases", "examples,fuzzing",
    "--mode", "positive",
    "--max-examples", $MaxExamples.ToString(),
    "--workers", "1",
    "--max-failures", "1",
    "--request-timeout", $RequestTimeoutSeconds.ToString(),
    "--request-retries", "0",
    "--max-redirects", "0",
    "--generation-deterministic",
    "--output-sanitize", "true",
    "--no-color"
)

& $schemathesisPath @schemathesisArguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
