#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$Tag,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# DEVELOPMENT ONLY. These images and their smoke environment are not a production release.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($EnvFile)) { $EnvFile = Join-Path $projectRoot ".env" }

function Resolve-RequiredCommand {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "缺少必要工具 '$Name'。請先安裝後重新執行。" }
    return $command.Source
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$FailureMessage
    )
    $display = "$Executable " + (($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join ' ')
    if ($DryRun) {
        Write-Host "[DRY-RUN] $display" -ForegroundColor Yellow
        return @()
    }
    $output = @(& $Executable @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | ForEach-Object { [string]$_ }) -join "`n"
        throw "$FailureMessage`n命令：$display`n$detail"
    }
    return $output
}

function Wait-ContainerHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Container,
        [ValidateRange(5, 180)][int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $state = ((& $script:Docker inspect --format "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}" $Container 2>$null) -join "").Trim()
        if ($LASTEXITCODE -ne 0) { throw "無法讀取驗收container '$Container'。" }
        if ($state -eq "running|healthy") { return }
        if ($state -match '^exited\|') {
            $logs = ((& $script:Docker logs $Container 2>&1) | ForEach-Object { [string]$_ }) -join "`n"
            throw "驗收container '$Container'提前結束。`n$logs"
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    $logs = ((& $script:Docker logs $Container 2>&1) | ForEach-Object { [string]$_ }) -join "`n"
    throw "驗收container '$Container'未在${TimeoutSeconds}秒內healthy。`n$logs"
}

function Get-PublishedPort {
    param([Parameter(Mandatory = $true)][string]$Container)
    $line = ((& $script:Docker port $Container "8080/tcp" 2>$null) -join "").Trim()
    if ($LASTEXITCODE -ne 0 -or $line -notmatch ':(\d+)$') {
        throw "無法取得container '$Container'的本機驗收port。"
    }
    return [int]$Matches[1]
}

function Assert-Http200 {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
    }
    catch {
        throw "$Name 驗收失敗：$Url；$($_.Exception.Message)"
    }
    if ([int]$response.StatusCode -ne 200) { throw "$Name 驗收失敗：HTTP $($response.StatusCode)。" }
    Write-Host "[PASS] $Name — HTTP 200" -ForegroundColor Green
}

$script:Docker = Resolve-RequiredCommand -Name "docker"
$git = Resolve-RequiredCommand -Name "git"
$requiredFiles = @(
    "pyproject.toml", "uv.lock",
    "docker/compat/Dockerfile.api", "docker/compat/Dockerfile.api.dockerignore",
    "docker/compat/Dockerfile.ui", "docker/compat/Dockerfile.ui.dockerignore",
    "docker/compat/Dockerfile.runtime-ops", "docker/compat/Dockerfile.runtime-ops.dockerignore"
)
$missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf) })
if ($missing.Count -gt 0) { throw "缺少image建置檔案：$($missing -join ', ')" }

if (-not $DryRun) {
    & $script:Docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon無法使用。請啟動Docker Desktop後重試。" }
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        throw "找不到本機驗收env file：$EnvFile。它只供本機container驗收，不會複製進image。"
    }
}

$head = ((& $git -C $projectRoot rev-parse --short=12 HEAD) -join "").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($head)) { throw "無法取得Git HEAD，停止建立image。" }
if ([string]::IsNullOrWhiteSpace($Tag)) { $Tag = "compat-$head" }
if ($Tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { throw "image tag格式無效：$Tag" }

$images = [ordered]@{
    Api = "union-api-compat:$Tag"
    Ui = "union-ui-compat:$Tag"
    RuntimeOps = "union-runtime-ops-compat:$Tag"
}
$dockerfiles = [ordered]@{
    Api = "docker/compat/Dockerfile.api"
    Ui = "docker/compat/Dockerfile.ui"
    RuntimeOps = "docker/compat/Dockerfile.runtime-ops"
}

Write-Host "=== Dockerfile檢查與三個compat images建置 ===" -ForegroundColor Cyan
Push-Location $projectRoot
try {
    foreach ($role in $dockerfiles.Keys) {
        $dockerfile = $dockerfiles[$role]
        Invoke-CheckedCommand -Executable $script:Docker -Arguments @("build", "--check", "-f", $dockerfile, ".") `
            -FailureMessage "$role Dockerfile check失敗。"
        Invoke-CheckedCommand -Executable $script:Docker -Arguments @(
            "build", "--pull", "--build-arg", "APP_RELEASE_VERSION=$head", "-f", $dockerfile,
            "-t", $images[$role], "."
        ) -FailureMessage "$role image建置失敗。"
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] 將驗證non-root、imports、runtime check、API/UI health及UI→API。" -ForegroundColor Yellow
        [pscustomobject]@{ Api = $images.Api; Ui = $images.Ui; RuntimeOps = $images.RuntimeOps; Tag = $Tag; Head = $head }
        return
    }

    Write-Host "=== 靜態image驗收 ===" -ForegroundColor Cyan
    foreach ($role in $images.Keys) {
        $runtimeUser = ((& $script:Docker image inspect $images[$role] --format "{{.Config.User}}") -join "").Trim()
        if ($LASTEXITCODE -ne 0 -or $runtimeUser -ne "10001:10001") {
            throw "$role image必須以10001:10001執行，目前為'$runtimeUser'。"
        }
        Write-Host "[PASS] $role non-root user=$runtimeUser" -ForegroundColor Green
    }
    Invoke-CheckedCommand -Executable $script:Docker -Arguments @("run", "--rm", $images.Ui, "python", "-c", "import google.auth; import ui.app") `
        -FailureMessage "UI built-image import gate失敗；請檢查compat-ui直接相依。"
    Invoke-CheckedCommand -Executable $script:Docker -Arguments @("run", "--rm", $images.Api, "python", "-c", "import api.main") `
        -FailureMessage "API built-image import gate失敗。"
    $apiContainer = "union-api-compat-accept-$PID"
    $uiContainer = "union-ui-compat-accept-$PID"
    $runtimeEnvPath = Join-Path ([System.IO.Path]::GetTempPath()) "union-compat-runtime-accept-$PID.env"
    $apiOverrideEnvPath = Join-Path ([System.IO.Path]::GetTempPath()) "union-compat-api-accept-$PID.env"
    try {
        $mysqlContainer = "mysql_db"
        foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding utf8) {
            if ($line -match '^\s*MYSQL_CONTAINER\s*=\s*(.+?)\s*$') { $mysqlContainer = $Matches[1].Trim() }
        }
        $mysqlRunning = ((& $script:Docker inspect --format "{{.State.Running}}" $mysqlContainer 2>$null) -join "").Trim()
        if ($LASTEXITCODE -ne 0 -or $mysqlRunning -ne "true") {
            throw "本機image驗收需要運行中的MySQL container '$mysqlContainer'。"
        }
        $networkLines = @(& $script:Docker inspect $mysqlContainer --format "{{range `$name,`$value := .NetworkSettings.Networks}}{{println `$name}}{{end}}")
        if ($LASTEXITCODE -ne 0) { throw "無法取得MySQL container network。" }
        $network = [string]($networkLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
        if ([string]::IsNullOrWhiteSpace($network)) { throw "MySQL container沒有可用Docker network。" }

        $keyBytes = [byte[]]::new(32)
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
        $smokeKey = [Convert]::ToBase64String($keyBytes)
        @(
            "APP_ENV=test",
            "INTERNAL_SERVICE_AUTH_MODE=local_shared_key",
            "INTERNAL_SERVICE_SHARED_KEY=$smokeKey",
            "INTERNAL_API_BASE_URL=http://${apiContainer}:8080",
            "INTERNAL_SERVICE_NAME=durable-job-worker"
        ) | Set-Content -LiteralPath $runtimeEnvPath -Encoding utf8NoBOM
        @(
            "APP_ENV=test",
            "INTERNAL_SERVICE_AUTH_MODE=local_shared_key",
            "INTERNAL_SERVICE_SHARED_KEY=$smokeKey",
            "DB_HOST=$mysqlContainer",
            "DB_PORT=3306"
        ) | Set-Content -LiteralPath $apiOverrideEnvPath -Encoding utf8NoBOM

        Invoke-CheckedCommand -Executable $script:Docker -Arguments @(
            "run", "--rm", "-d", "--name", $apiContainer, "--network", $network,
            "-p", "127.0.0.1::8080", "--env-file", $EnvFile, "--env-file", $apiOverrideEnvPath,
            "-e", "PORT=8080", $images.Api
        ) -FailureMessage "API驗收container啟動失敗。"
        Wait-ContainerHealth -Container $apiContainer -TimeoutSeconds 120
        $apiPort = Get-PublishedPort -Container $apiContainer
        Assert-Http200 -Name "API /health" -Url "http://127.0.0.1:$apiPort/health"
        Assert-Http200 -Name "API /openapi.json" -Url "http://127.0.0.1:$apiPort/openapi.json"

        $privateProbe = @"
import datetime, os, requests
payload = {'worker_id': 'image-acceptance', 'runtime_identity': {'service_name': 'durable-job-worker', 'instance_id': 'image-acceptance', 'process_id': 0, 'hostname': 'container', 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'release_version': 'image-acceptance'}, 'lease_seconds': 60, 'retry_delay_seconds': 15, 'check_only': True}
r = requests.post(os.environ['INTERNAL_API_BASE_URL'] + '/internal/v1/runtime/durable-jobs/run-once', json=payload, headers={'X-Internal-Service-Name': 'durable-job-worker', 'X-Internal-Service-Key': os.environ['INTERNAL_SERVICE_SHARED_KEY']}, timeout=20)
print(r.status_code, r.text)
raise SystemExit(0 if r.status_code == 200 else 1)
"@
        Invoke-CheckedCommand -Executable $script:Docker -Arguments @(
            "run", "--rm", "--network", $network, "--env-file", $runtimeEnvPath,
            $images.RuntimeOps, "python", "-c", $privateProbe
        ) -FailureMessage "runtime-ops到Private API的typed durable check失敗。"
        try {
            Invoke-CheckedCommand -Executable $script:Docker -Arguments @(
                "run", "--rm", "--network", $network, "--env-file", $runtimeEnvPath,
                $images.RuntimeOps, "python", "-m", "scripts.run_durable_job_worker", "--check"
            ) -FailureMessage "runtime-ops durable worker --check失敗。"
        }
        catch {
            $apiLogs = ((& $script:Docker logs $apiContainer 2>&1) | ForEach-Object { [string]$_ }) -join "`n"
            throw "$($_.Exception.Message)`nAPI container logs：`n$apiLogs"
        }
        Write-Host "[PASS] runtime-ops Private API --check（未注入DB credential）" -ForegroundColor Green

        Invoke-CheckedCommand -Executable $script:Docker -Arguments @(
            "run", "--rm", "-d", "--name", $uiContainer, "--network", $network,
            "-p", "127.0.0.1::8080", "-e", "PORT=8080", "-e", "APP_ENV=staging",
            "-e", "API_BASE_URL=http://${apiContainer}:8080", "-e", "UI_API_AUTH_MODE=none", $images.Ui
        ) -FailureMessage "UI驗收container啟動失敗。"
        Wait-ContainerHealth -Container $uiContainer -TimeoutSeconds 120
        $uiPort = Get-PublishedPort -Container $uiContainer
        Assert-Http200 -Name "UI Streamlit health" -Url "http://127.0.0.1:$uiPort/_stcore/health"
        Assert-Http200 -Name "UI首頁" -Url "http://127.0.0.1:$uiPort/"
        Invoke-CheckedCommand -Executable $script:Docker -Arguments @(
            "exec", $uiContainer, "python", "-c",
            "from urllib.request import urlopen; r=urlopen('http://${apiContainer}:8080/health', timeout=10); raise SystemExit(0 if r.status == 200 else 1)"
        ) -FailureMessage "UI container到API container連線驗收失敗。"
        Write-Host "[PASS] UI → API container wiring" -ForegroundColor Green
    }
    finally {
        foreach ($container in @($uiContainer, $apiContainer)) {
            & $script:Docker rm -f $container *> $null
        }
        Remove-Item -LiteralPath $runtimeEnvPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $apiOverrideEnvPath -Force -ErrorAction SilentlyContinue
    }

    $receiptDirectory = Join-Path $projectRoot "scratch\cloud-run-compat-build"
    New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null
    $receiptPath = Join-Path $receiptDirectory "latest-image-acceptance.json"
    $receipt = [ordered]@{
        status = "PASS"
        head = $head
        tag = $Tag
        created_at = (Get-Date).ToUniversalTime().ToString("o")
        images = [ordered]@{}
    }
    foreach ($role in $images.Keys) {
        $imageId = ((& $script:Docker image inspect $images[$role] --format "{{.Id}}") -join "").Trim()
        $receipt.images[$role] = [ordered]@{ reference = $images[$role]; image_id = $imageId }
    }
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding utf8NoBOM
    Write-Host "本機image驗收receipt：$receiptPath"
    [pscustomobject]@{ Api = $images.Api; Ui = $images.Ui; RuntimeOps = $images.RuntimeOps; Tag = $Tag; Head = $head; Receipt = $receiptPath }
}
finally {
    Pop-Location
}
