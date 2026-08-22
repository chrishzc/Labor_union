#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$ProjectId,
    [string]$Region = "asia-east1",
    [string]$Repository,
    [string]$Network = "union-compat-vpc",
    [string]$Subnet = "union-compat-run",
    [string]$DbHost,
    [int]$DbPort = 13306,
    [string]$DbUser,
    [string]$DbDatabase,
    [string]$DbPasswordSecret = "union-db-password-compat",
    [string]$TotpKeyringSecret = "union-totp-keyring-compat",
    [string]$LineChannelSecretSecret = "union-line-channel-secret-compat",
    [string]$LineAccessTokenSecret = "union-line-access-token-compat",
    [string]$LineLiffId,
    [string]$LineLoginChannelId,
    [string]$ApiImage,
    [string]$UiImage,
    [string]$RuntimeOpsImage,
    [ValidateSet("api", "ui", "runtime-ops")][string[]]$Roles = @("api", "ui", "runtime-ops"),
    [switch]$SelectExistingImages,
    [switch]$PreflightOnly,
    [switch]$InitialProvision,
    [switch]$DryRun,
    [switch]$AssumeNewProject
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# DEVELOPMENT ONLY. This publisher targets the disposable compatibility environment.
# It must never be used for production or as a substitute for Cloud VPN -> NAS.

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Resolve-Executable {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = if ($Name -eq "gcloud") {
        Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    else { $null }
    if ($null -eq $command) { $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if ($null -eq $command) {
        throw "找不到必要工具 '$Name'。請先安裝並確認它位於 PATH。"
    }
    return $command.Source
}

function Assert-PublisherPrerequisites {
    $failures = [System.Collections.Generic.List[string]]::new()
    if ($PSVersionTable.PSVersion.Major -lt 7) { $failures.Add("需要PowerShell 7以上；請使用pwsh執行。") }
    foreach ($name in @("git", "docker", "gcloud")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (($null -eq $command) -and ($name -eq "gcloud")) {
            $command = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
        }
        if ($null -eq $command) { $failures.Add("缺少工具'$name'；請安裝並加入PATH。") }
    }
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    foreach ($relativePath in @(
        "pyproject.toml", "uv.lock",
        "docker/compat/Dockerfile.api", "docker/compat/Dockerfile.ui", "docker/compat/Dockerfile.runtime-ops",
        "scripts/launchers/build_and_validate_cloud_run_compat_images.ps1"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
            $failures.Add("缺少必要檔案'$relativePath'；請確認已完整clone／pull repository。")
        }
    }
    $docker = Get-Command "docker" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $docker) {
        & $docker.Source info *> $null
        if ($LASTEXITCODE -ne 0) { $failures.Add("Docker CLI存在但daemon無法使用；請啟動Docker Desktop。") }
    }
    if ($failures.Count -gt 0) {
        $numbered = for ($index = 0; $index -lt $failures.Count; $index++) { "[$($index + 1)] $($failures[$index])" }
        throw "發布前置檢查失敗：`n$($numbered -join "`n")"
    }
    Write-Host "[PASS] publisher prerequisites：PowerShell、Git、Docker、gcloud及三份Dockerfile。" -ForegroundColor Green
}

function Format-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $displayArgs = foreach ($argument in $Arguments) {
        if ($argument -match '\s') {
            '"{0}"' -f ($argument -replace '"', '\"')
        }
        else {
            $argument
        }
    }
    return ((Split-Path -Leaf $Executable) + " " + ($displayArgs -join " "))
}

function Invoke-NativeRead {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $leaf = Split-Path -Leaf $Executable
    $maxAttempts = if ($leaf -match '^gcloud(?:\.cmd)?$') { 6 } elseif (($leaf -match '^docker(?:\.exe)?$') -and ($Arguments[0] -eq "push")) { 5 } else { 1 }
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $Executable
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        foreach ($argument in $Arguments) { $null = $startInfo.ArgumentList.Add($argument) }
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        $output = @($stdout -split "`r?`n" | Where-Object { -not [string]::IsNullOrEmpty($_) })
        $detail = (($stdout, $stderr) -join "`n").Trim()
        $retryable = $detail -match '(?i)(HTTP\s*429|RESOURCE_EXHAUSTED|rateLimitExceeded|too many requests|service.+not enabled|has not been used.+before|propagation|please retry|unexpected EOF|server error)'
        if (($exitCode -eq 0) -or (-not $retryable) -or ($attempt -eq $maxAttempts)) { break }
        $delay = [Math]::Min(30, [Math]::Pow(2, $attempt)) + (Get-Random -Minimum 0 -Maximum 3)
        Write-Warning "遠端服務暫時性錯誤；$delay 秒後重試（$attempt/$maxAttempts）。"
        Start-Sleep -Seconds $delay
    }
    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        throw "命令失敗（exit=$exitCode）：$(Format-Command -Executable $Executable -Arguments $Arguments)`n$detail"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = @($output)
    }
}

function Invoke-NativeMutation {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $display = Format-Command -Executable $Executable -Arguments $Arguments
    if ($DryRun) {
        Write-Host "[DRY-RUN] $display" -ForegroundColor Yellow
        return
    }
    Write-Host "[EXEC] $display" -ForegroundColor DarkGray
    $leaf = Split-Path -Leaf $Executable
    $maxAttempts = if ($leaf -match '^gcloud(?:\.cmd)?$') { 6 } elseif (($leaf -match '^docker(?:\.exe)?$') -and ($Arguments[0] -eq "push")) { 5 } else { 1 }
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $nativeOutput = @(& $Executable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        $detail = ($nativeOutput | ForEach-Object { [string]$_ }) -join "`n"
        $retryable = $detail -match '(?i)(HTTP\s*429|RESOURCE_EXHAUSTED|rateLimitExceeded|too many requests|service.+not enabled|has not been used.+before|propagation|please retry|unexpected EOF|server error)'
        if (($exitCode -eq 0) -or (-not $retryable) -or ($attempt -eq $maxAttempts)) { break }
        $delay = [Math]::Min(30, [Math]::Pow(2, $attempt)) + (Get-Random -Minimum 0 -Maximum 3)
        Write-Warning "遠端服務暫時性錯誤；$delay 秒後重試（$attempt/$maxAttempts）。"
        Start-Sleep -Seconds $delay
    }
    if ($nativeOutput.Count -gt 0) { $nativeOutput | Out-Host }
    if ($exitCode -ne 0) {
        throw "命令失敗（exit=$exitCode）：$display`n$detail"
    }
}

function ConvertFrom-JsonOutput {
    param([Parameter(Mandatory = $true)][object[]]$Output)
    $text = ($Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return @()
    }
    return @($text | ConvertFrom-Json)
}

function Read-RequiredValue {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$Default,
        [scriptblock]$Validator,
        [string]$ValidationMessage = "輸入格式不正確。"
    )
    while ($true) {
        $suffix = ""
        if (-not [string]::IsNullOrWhiteSpace($Default)) {
            $suffix = " [$Default]"
        }
        $value = (Read-Host "$Prompt$suffix").Trim()
        if ([string]::IsNullOrWhiteSpace($value)) {
            $value = $Default
        }
        if ([string]::IsNullOrWhiteSpace($value)) {
            Write-Warning "此欄位不可留空。"
            continue
        }
        if (($null -ne $Validator) -and (-not (& $Validator $value))) {
            Write-Warning $ValidationMessage
            continue
        }
        return $value
    }
}

function Read-SingleSelection {
    param(
        [Parameter(Mandatory = $true)][object[]]$Items,
        [Parameter(Mandatory = $true)][scriptblock]$Formatter,
        [Parameter(Mandatory = $true)][string]$Prompt
    )
    if ($Items.Count -eq 0) {
        throw "沒有可供選擇的項目。"
    }
    for ($index = 0; $index -lt $Items.Count; $index++) {
        Write-Host ("[{0}] {1}" -f ($index + 1), (& $Formatter $Items[$index]))
    }
    while ($true) {
        $raw = (Read-Host $Prompt).Trim()
        $number = 0
        if ([int]::TryParse($raw, [ref]$number) -and ($number -ge 1) -and ($number -le $Items.Count)) {
            return $Items[$number - 1]
        }
        Write-Warning "請輸入 1 到 $($Items.Count) 之間的項次。"
    }
}

function Read-MultipleSelection {
    param(
        [Parameter(Mandatory = $true)][object[]]$Items,
        [Parameter(Mandatory = $true)][scriptblock]$Formatter,
        [Parameter(Mandatory = $true)][string]$Prompt
    )
    if ($Items.Count -eq 0) {
        throw "沒有可供選擇的項目。"
    }
    for ($index = 0; $index -lt $Items.Count; $index++) {
        Write-Host ("[{0}] {1}" -f ($index + 1), (& $Formatter $Items[$index]))
    }
    while ($true) {
        $raw = (Read-Host $Prompt).Trim()
        $tokens = @($raw -split '\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        $indices = [System.Collections.Generic.List[int]]::new()
        $valid = $tokens.Count -gt 0
        foreach ($token in $tokens) {
            $number = 0
            if ((-not [int]::TryParse($token, [ref]$number)) -or ($number -lt 1) -or ($number -gt $Items.Count)) {
                $valid = $false
                break
            }
            if (-not $indices.Contains($number - 1)) {
                $indices.Add($number - 1)
            }
        }
        if ($valid -and ($indices.Count -gt 0)) {
            $selected = foreach ($index in $indices) { $Items[$index] }
            return @($selected)
        }
        Write-Warning "請以空格分隔有效項次，例如：1 2 4。"
    }
}

function Read-ConfirmationToken {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    if ($DryRun) {
        return $true
    }
    $actual = (Read-Host "$Prompt（輸入 $Expected）").Trim()
    return $actual -ceq $Expected
}

function ConvertTo-DockerAlias {
    param([Parameter(Mandatory = $true)][string]$Value)
    $leaf = ($Value -split '/')[-1].ToLowerInvariant()
    $safe = $leaf -replace '[^a-z0-9._-]', '-'
    $safe = $safe.Trim('.', '-', '_')
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "image-compat"
    }
    return $safe
}

function Test-GcloudResource {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $script:Gcloud @Arguments *> $null
    return $LASTEXITCODE -eq 0
}

function Get-ProjectSelection {
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "projects", "list", "--filter=lifecycleState:ACTIVE", "--format=json"
    )
    $projects = @(ConvertFrom-JsonOutput -Output $result.Output | Where-Object {
        if (-not $_.PSObject.Properties["labels"]) { return $false }
        $environment = ""
        $deployment = ""
        if ($_.labels.PSObject.Properties["environment"]) { $environment = [string]$_.labels.environment }
        if ($_.labels.PSObject.Properties["deployment"]) { $deployment = [string]$_.labels.deployment }
        return ($environment -in @("staging", "test")) -and ($deployment -eq "compat")
    })
    return Read-SingleSelection -Items $projects -Prompt "選擇 GCP Project 項次" -Formatter {
        param($item)
        "$($item.projectId) — $($item.name)"
    }
}

function Assert-CompatibilityProject {
    param([Parameter(Mandatory = $true)][string]$TargetProjectId)
    if ($AssumeNewProject -and $DryRun) {
        return
    }
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "projects", "describe", $TargetProjectId, "--format=json"
    )
    $project = (ConvertFrom-JsonOutput -Output $result.Output)[0]
    $environment = ""
    $deployment = ""
    if ($null -ne $project.labels) {
        $environmentProperty = $project.labels.PSObject.Properties["environment"]
        $deploymentProperty = $project.labels.PSObject.Properties["deployment"]
        if ($null -ne $environmentProperty) { $environment = [string]$environmentProperty.Value }
        if ($null -ne $deploymentProperty) { $deployment = [string]$deploymentProperty.Value }
    }
    if (($environment -notin @("staging", "test")) -or ($deployment -ne "compat")) {
        throw "目標 Project '$TargetProjectId' 缺少 environment=staging|test 與 deployment=compat 標籤。為避免誤部署 production，腳本已停止。"
    }
}

function Get-RepositorySelection {
    param(
        [Parameter(Mandatory = $true)][string]$TargetProjectId,
        [Parameter(Mandatory = $true)][string]$TargetRegion
    )
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "artifacts", "repositories", "list",
        "--project=$TargetProjectId", "--location=$TargetRegion", "--format=json"
    )
    $repositories = @(ConvertFrom-JsonOutput -Output $result.Output | Where-Object { $_.format -eq "DOCKER" })
    return Read-SingleSelection -Items $repositories -Prompt "選擇 Artifact Registry 倉庫項次" -Formatter {
        param($item)
        $immutable = "mutable-tags"
        if ($item.PSObject.Properties["dockerConfig"] -and $item.dockerConfig.immutableTags) {
            $immutable = "immutable-tags"
        }
        "$($item.name.Split('/')[-1]) — $immutable"
    }
}

function Get-LocalDockerImages {
    $result = Invoke-NativeRead -Executable $script:Docker -Arguments @(
        "image", "ls", "--format", "{{json .}}"
    )
    $images = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $result.Output) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $item = $line | ConvertFrom-Json
        if (($item.Repository -eq "<none>") -or ($item.Tag -eq "<none>")) { continue }
        $reference = "$($item.Repository):$($item.Tag)"
        if ($seen.Add($reference)) {
            $images.Add([pscustomobject]@{
                Reference = $reference
                Repository = [string]$item.Repository
                Tag = [string]$item.Tag
                Id = [string]$item.ID
                CreatedSince = [string]$item.CreatedSince
                Size = [string]$item.Size
            })
        }
    }
    return @($images)
}

function Show-RemoteImages {
    param([Parameter(Mandatory = $true)][string]$RegistryRoot)
    Write-Section "Artifact Registry 目前內容"
    if ($AssumeNewProject -and $DryRun) {
        Write-Host "[DRY-RUN] 新 Project／倉庫尚未建立，沒有遠端 image 可查詢。"
        return
    }
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "artifacts", "docker", "images", "list", $RegistryRoot,
        "--include-tags", "--format=table(package,version,tags,updateTime)"
    ) -AllowFailure
    if ($result.ExitCode -ne 0) {
        throw "無法查詢 Artifact Registry '$RegistryRoot'。請確認權限與倉庫地區。"
    }
    if ($result.Output.Count -eq 0) {
        Write-Host "倉庫目前沒有 images。"
    }
    else {
        $result.Output | ForEach-Object { Write-Host $_ }
    }
}

function Show-CloudRunResources {
    Write-Section "目前 Cloud Run compat 資源"
    if ($AssumeNewProject -and $DryRun) {
        Write-Host "[DRY-RUN] 新 Project 尚未建立，沒有既有 Cloud Run 資源。"
        return
    }
    $queries = @(
        [pscustomobject]@{ Label = "Services"; Arguments = @("run", "services", "list", "--project=$ProjectId", "--region=$Region", "--filter=metadata.name~compat", "--format=table(metadata.name,status.url)") },
        [pscustomobject]@{ Label = "Worker Pools"; Arguments = @("run", "worker-pools", "list", "--project=$ProjectId", "--region=$Region", "--filter=metadata.name~compat", "--format=table(metadata.name)") },
        [pscustomobject]@{ Label = "Jobs"; Arguments = @("run", "jobs", "list", "--project=$ProjectId", "--region=$Region", "--filter=metadata.name~compat", "--format=table(metadata.name)") }
    )
    foreach ($query in $queries) {
        Write-Host "[$($query.Label)]"
        $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments $query.Arguments -AllowFailure
        if (($result.ExitCode -eq 0) -and ($result.Output.Count -gt 0)) {
            $result.Output | ForEach-Object { Write-Host $_ }
        }
        else {
            Write-Host "（無或目前無法查詢）"
        }
    }
    Write-Host "部署用途固定映射到上述官方compat拓樸；腳本不允許任意覆寫其他Cloud Run資源。"
}

function Get-RoleChoice {
    param([Parameter(Mandatory = $true)][string]$ImageReference)
    Write-Host ""
    Write-Host "設定 $ImageReference 的用途："
    Write-Host "[1] API — union-api-compat Cloud Run Service"
    Write-Host "[2] UI — union-ui-compat Cloud Run Service"
    Write-Host "[3] runtime-ops — 三個 Worker Pools + Monitor Job"
    Write-Host "[4] 只 push，不部署"
    while ($true) {
        $choice = (Read-Host "輸入用途項次").Trim()
        switch ($choice) {
            "1" { return "api" }
            "2" { return "ui" }
            "3" { return "runtime-ops" }
            "4" { return "push-only" }
            default { Write-Warning "請輸入 1、2、3 或 4。" }
        }
    }
}

function Get-DefaultAliasForRole {
    param(
        [Parameter(Mandatory = $true)][string]$Role,
        [Parameter(Mandatory = $true)][string]$LocalRepository
    )
    switch ($Role) {
        "api" { return "union-api-compat" }
        "ui" { return "union-ui-compat" }
        "runtime-ops" { return "union-runtime-ops-compat" }
        default {
            $candidate = ConvertTo-DockerAlias -Value $LocalRepository
            if ($candidate -notmatch '(compat|test)') { $candidate = "$candidate-compat" }
            return $candidate
        }
    }
}

function Test-RemoteTagExists {
    param([Parameter(Mandatory = $true)][string]$RemoteReference)
    if ($AssumeNewProject -and $DryRun) {
        return $false
    }
    return Test-GcloudResource -Arguments @(
        "artifacts", "docker", "images", "describe", $RemoteReference,
        "--project=$ProjectId"
    )
}

function Resolve-RemoteDigestReference {
    param([Parameter(Mandatory = $true)][string]$RemoteReference)
    if ($DryRun) {
        return "$($RemoteReference.Split(':')[0])@sha256:<resolved-after-push>"
    }
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "artifacts", "docker", "images", "describe", $RemoteReference,
        "--project=$ProjectId", "--format=value(image_summary.digest)"
    )
    $digest = (($result.Output -join "").Trim())
    if ($digest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw "已 push '$RemoteReference'，但無法取得有效 digest；停止部署以避免使用 mutable tag。"
    }
    $withoutTag = $RemoteReference.Substring(0, $RemoteReference.LastIndexOf(':'))
    return "$withoutTag@$digest"
}

function Ensure-ApiInvoker {
    param([Parameter(Mandatory = $true)][string]$ServiceAccount)
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "run", "services", "add-iam-policy-binding", "union-api-compat",
        "--project=$ProjectId", "--region=$Region",
        "--member=serviceAccount:$ServiceAccount", "--role=roles/run.invoker", "--quiet"
    )
}

function Get-ServiceAccountEmail {
    param([Parameter(Mandatory = $true)][string]$AccountId)
    return "$AccountId@$ProjectId.iam.gserviceaccount.com"
}

function Assert-ServiceAccountExists {
    param([Parameter(Mandatory = $true)][string]$AccountId)
    if ($AssumeNewProject -and $DryRun) { return }
    $email = Get-ServiceAccountEmail -AccountId $AccountId
    if (-not (Test-GcloudResource -Arguments @(
        "iam", "service-accounts", "describe", $email, "--project=$ProjectId"
    ))) {
        throw "缺少必要Service Account：$email。請先執行首次設定腳本。"
    }
}

function Deploy-ApiImage {
    param([Parameter(Mandatory = $true)][string]$DigestReference)
    $service = "union-api-compat"
    $apiSa = Get-ServiceAccountEmail -AccountId "union-api-compat"
    $durableSa = Get-ServiceAccountEmail -AccountId "union-durable-compat"
    $lineSa = Get-ServiceAccountEmail -AccountId "union-line-compat"
    $incidentSa = Get-ServiceAccountEmail -AccountId "union-incident-compat"
    $monitorSa = Get-ServiceAccountEmail -AccountId "union-monitor-compat"
    $exists = (-not ($AssumeNewProject -and $DryRun)) -and (Test-GcloudResource -Arguments @(
        "run", "services", "describe", $service, "--project=$ProjectId", "--region=$Region"
    ))
    if ($exists) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "run", "services", "update", $service, "--project=$ProjectId", "--region=$Region",
            "--image=$DigestReference", "--quiet"
        )
        return
    }
    if (-not $InitialProvision) {
        throw "union-api-compat 不存在；更新腳本禁止建立資源，請先執行首次開發部署腳本。"
    }
    foreach ($required in @($DbHost, $DbUser, $DbDatabase, $LineLiffId, $LineLoginChannelId)) {
        if ([string]::IsNullOrWhiteSpace([string]$required)) {
            throw "首次部署缺少 DB／LINE runtime 設定。"
        }
    }
    $allowedCallers = "durable-job-worker=$durableSa,line-worker=$lineSa,incident-worker=$incidentSa,runtime-monitor=$monitorSa"
    $environment = "^|^APP_ENV=staging|DEPLOYMENT_PROFILE=development_gce_iap_reverse_ssh|DB_HOST=$DbHost|DB_PORT=$DbPort|DB_USER=$DbUser|DB_DATABASE=$DbDatabase|DB_SSL_MODE=disabled|REDIS_URL=|DEV_REVIEW_NOTIFY_URL=|ENABLE_ADMIN_AUTH=true|ACCESS_CONTROL_PROFILE=production|ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION=v1|LINE_WEBHOOK_RUNTIME_MODE=canonical|LINE_WORKER_RUNTIME_MODE=canonical|LINE_LIFF_ID=$LineLiffId|LINE_LOGIN_CHANNEL_ID=$LineLoginChannelId|LIFF_REQUIRE_ID_TOKEN=true|INTERNAL_SERVICE_AUTH_MODE=google_oidc|INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS=$allowedCallers|INTERNAL_API_MAX_ATTEMPTS=3|KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED=false"
    $secrets = "DB_PASSWORD=$DbPasswordSecret`:latest,ACCESS_CONTROL_TOTP_KEYRING=$TotpKeyringSecret`:latest,LINE_CHANNEL_SECRET=$LineChannelSecretSecret`:latest,LINE_CHANNEL_ACCESS_TOKEN=$LineAccessTokenSecret`:latest"
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "run", "deploy", $service, "--project=$ProjectId", "--region=$Region",
        "--image=$DigestReference", "--execution-environment=gen2", "--service-account=$apiSa",
        "--labels=environment=staging,deployment=compat",
        "--cpu=1", "--memory=1Gi", "--min=0", "--max=1", "--concurrency=20", "--timeout=60",
        "--ingress=all", "--allow-unauthenticated",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--network-tags=cr-api-compat", "--set-env-vars=$environment", "--set-secrets=$secrets", "--quiet"
    )
}

function Get-ApiUrl {
    if ($DryRun -and $AssumeNewProject) {
        return "https://union-api-compat-<generated>.$Region.run.app"
    }
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "run", "services", "describe", "union-api-compat", "--project=$ProjectId", "--region=$Region",
        "--format=value(status.url)"
    )
    $url = (($result.Output -join "").Trim())
    if ([string]::IsNullOrWhiteSpace($url)) {
        throw "找不到 union-api-compat URL；UI／runtime-ops 無法串聯。"
    }
    return $url
}

function Complete-InitialApiConfiguration {
    param([Parameter(Mandatory = $true)][string]$ApiUrl)
    if (-not $InitialProvision) { return }
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "run", "services", "update", "union-api-compat", "--project=$ProjectId", "--region=$Region",
        "--update-env-vars=INTERNAL_SERVICE_OIDC_AUDIENCE=$ApiUrl,LINE_PUBLIC_BASE_URL=$ApiUrl", "--quiet"
    )
    Ensure-ApiInvoker -ServiceAccount (Get-ServiceAccountEmail -AccountId "union-ui-compat")
}

function Complete-InitialMonitorConfiguration {
    param(
        [Parameter(Mandatory = $true)][string]$ApiUrl,
        [Parameter(Mandatory = $true)][string]$UiUrl
    )
    if (-not $InitialProvision) { return }
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "run", "jobs", "update", "union-monitor-compat", "--project=$ProjectId", "--region=$Region",
        "--update-env-vars=API_HEALTH_URL=$ApiUrl/health,UI_HEALTH_URL=$UiUrl/_stcore/health,LINE_PUBLIC_BASE_URL=$ApiUrl,LINE_LIFF_HEALTH_URL=$ApiUrl/liff-page",
        "--quiet"
    )
}

function Deploy-UiImage {
    param(
        [Parameter(Mandatory = $true)][string]$DigestReference,
        [Parameter(Mandatory = $true)][string]$ApiUrl
    )
    $service = "union-ui-compat"
    $uiSa = Get-ServiceAccountEmail -AccountId "union-ui-compat"
    $exists = (-not ($AssumeNewProject -and $DryRun)) -and (Test-GcloudResource -Arguments @(
        "run", "services", "describe", $service, "--project=$ProjectId", "--region=$Region"
    ))
    if ($exists) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "run", "services", "update", $service, "--project=$ProjectId", "--region=$Region",
            "--image=$DigestReference", "--quiet"
        )
        return
    }
    if (-not $InitialProvision) {
        throw "union-ui-compat 不存在；更新腳本禁止建立資源，請先執行首次開發部署腳本。"
    }
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "run", "deploy", $service, "--project=$ProjectId", "--region=$Region",
        "--image=$DigestReference", "--execution-environment=gen2", "--service-account=$uiSa",
        "--labels=environment=staging,deployment=compat",
        "--cpu=1", "--memory=512Mi", "--min=0", "--max=1", "--concurrency=20", "--timeout=300",
        "--ingress=all", "--allow-unauthenticated",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--network-tags=cr-ui-compat", "--set-env-vars=APP_ENV=staging,DEPLOYMENT_PROFILE=development_gce_iap_reverse_ssh,ENABLE_ADMIN_AUTH=true,ACCESS_CONTROL_PROFILE=production,API_BASE_URL=$ApiUrl,UI_API_AUTH_MODE=google_oidc,UI_API_OIDC_AUDIENCE=$ApiUrl", "--quiet"
    )
    $activeAccountResult = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"
    )
    $activeAccount = [string]($activeAccountResult.Output | Select-Object -First 1)
    $activeAccount = $activeAccount.Trim()
    if (-not [string]::IsNullOrWhiteSpace($activeAccount)) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "run", "services", "add-iam-policy-binding", $service,
            "--project=$ProjectId", "--region=$Region", "--member=user:$activeAccount",
            "--role=roles/run.invoker", "--quiet"
        )
    }
}

function Deploy-RuntimeOpsImage {
    param(
        [Parameter(Mandatory = $true)][string]$DigestReference,
        [Parameter(Mandatory = $true)][string]$ApiUrl
    )
    $runtimeDefinitions = @(
        [pscustomobject]@{ Name = "union-durable-compat"; Account = "union-durable-compat"; Module = "scripts.run_durable_job_worker"; ServiceName = "durable-job-worker" },
        [pscustomobject]@{ Name = "union-line-compat"; Account = "union-line-compat"; Module = "scripts.run_line_worker"; ServiceName = "line-worker" },
        [pscustomobject]@{ Name = "union-incident-compat"; Account = "union-incident-compat"; Module = "scripts.run_incident_worker"; ServiceName = "incident-worker" }
    )
    foreach ($definition in $runtimeDefinitions) {
        $serviceAccount = Get-ServiceAccountEmail -AccountId $definition.Account
        $exists = (-not ($AssumeNewProject -and $DryRun)) -and (Test-GcloudResource -Arguments @(
            "run", "worker-pools", "describe", $definition.Name, "--project=$ProjectId", "--region=$Region"
        ))
        if ($exists) {
            Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
                "run", "worker-pools", "deploy", $definition.Name, "--project=$ProjectId", "--region=$Region",
                "--image=$DigestReference", "--quiet"
            )
        }
        else {
            if (-not $InitialProvision) {
                throw "$($definition.Name) 不存在；更新腳本禁止建立資源。"
            }
            $environment = "^|^APP_ENV=staging|REDIS_URL=|DEV_REVIEW_NOTIFY_URL=|INTERNAL_API_BASE_URL=$ApiUrl|INTERNAL_SERVICE_OIDC_AUDIENCE=$ApiUrl|INTERNAL_SERVICE_AUTH_MODE=google_oidc|INTERNAL_SERVICE_NAME=$($definition.ServiceName)|INTERNAL_API_MAX_ATTEMPTS=3"
            Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
                "run", "worker-pools", "deploy", $definition.Name, "--project=$ProjectId", "--region=$Region",
                "--image=$DigestReference", "--service-account=$serviceAccount", "--cpu=1", "--memory=512Mi",
                "--labels=environment=staging,deployment=compat",
                "--instances=1", "--command=python", "--args=-m,$($definition.Module)",
                "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
                "--network-tags=cr-runtime-compat", "--set-env-vars=$environment", "--quiet"
            )
        }
        if ($InitialProvision) { Ensure-ApiInvoker -ServiceAccount $serviceAccount }
    }

    $monitorName = "union-monitor-compat"
    $monitorSa = Get-ServiceAccountEmail -AccountId "union-monitor-compat"
    $monitorExists = (-not ($AssumeNewProject -and $DryRun)) -and (Test-GcloudResource -Arguments @(
        "run", "jobs", "describe", $monitorName, "--project=$ProjectId", "--region=$Region"
    ))
    if ($monitorExists) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "run", "jobs", "update", $monitorName, "--project=$ProjectId", "--region=$Region",
            "--image=$DigestReference", "--quiet"
        )
    }
    else {
        if (-not $InitialProvision) {
            throw "$monitorName 不存在；更新腳本禁止建立資源。"
        }
        $environment = "^|^APP_ENV=staging|REDIS_URL=|DEV_REVIEW_NOTIFY_URL=|INTERNAL_API_BASE_URL=$ApiUrl|INTERNAL_SERVICE_OIDC_AUDIENCE=$ApiUrl|INTERNAL_SERVICE_AUTH_MODE=google_oidc|INTERNAL_SERVICE_NAME=runtime-monitor|INTERNAL_API_MAX_ATTEMPTS=3|API_HEALTH_URL=$ApiUrl/health"
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "run", "jobs", "deploy", $monitorName, "--project=$ProjectId", "--region=$Region",
            "--image=$DigestReference", "--service-account=$monitorSa", "--cpu=1", "--memory=512Mi",
            "--labels=environment=staging,deployment=compat",
            "--tasks=1", "--max-retries=1", "--task-timeout=60s",
            "--command=python", "--args=-m,scripts.run_service_monitor,--once",
            "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
            "--network-tags=cr-monitor-compat", "--set-env-vars=$environment", "--quiet"
        )
    }
    if ($InitialProvision) { Ensure-ApiInvoker -ServiceAccount $monitorSa }
}

Write-Section "prerequisites集中預檢"
Assert-PublisherPrerequisites

Write-Section "工具檢查"
$script:Gcloud = Resolve-Executable -Name "gcloud"
$script:Docker = Resolve-Executable -Name "docker"
$script:Git = Resolve-Executable -Name "git"
Write-Host "gcloud: $script:Gcloud"
Write-Host "docker: $script:Docker"

if ($PreflightOnly) {
    $account = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"
    ) -AllowFailure
    $activeAccount = (($account.Output -join "").Trim())
    if ($account.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($activeAccount)) {
        throw "gcloud沒有active account；請先執行gcloud auth login。"
    }
    Write-Host "[PASS] gcloud active account：$activeAccount；未build、push或部署。" -ForegroundColor Green
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    Write-Section "選擇 GCP Project"
    $selectedProject = Get-ProjectSelection
    $ProjectId = [string]$selectedProject.projectId
}
Assert-CompatibilityProject -TargetProjectId $ProjectId

if ([string]::IsNullOrWhiteSpace($Repository)) {
    Write-Section "選擇 Artifact Registry 倉庫"
    $selectedRepository = Get-RepositorySelection -TargetProjectId $ProjectId -TargetRegion $Region
    $Repository = [string]$selectedRepository.name.Split('/')[-1]
}
elseif (-not ($AssumeNewProject -and $DryRun)) {
    if (-not (Test-GcloudResource -Arguments @(
        "artifacts", "repositories", "describe", $Repository,
        "--project=$ProjectId", "--location=$Region"
    ))) {
        throw "Artifact Registry 倉庫 '$Repository' 不存在於 $ProjectId/$Region。"
    }
}

$registryRoot = "$Region-docker.pkg.dev/$ProjectId/$Repository"
Write-Host "Project:    $ProjectId"
Write-Host "Region:     $Region"
Write-Host "Repository: $Repository"
Write-Host "Registry:   $registryRoot"

Show-RemoteImages -RegistryRoot $registryRoot

$usedRoles = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$plans = [System.Collections.Generic.List[object]]::new()
$providedImageCount = @(@($ApiImage, $UiImage, $RuntimeOpsImage) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
if (($providedImageCount -ne 0) -and ($providedImageCount -ne 3)) {
    throw "ApiImage、UiImage、RuntimeOpsImage必須三者全部提供，或全部省略。"
}

if ($SelectExistingImages) {
    if ($providedImageCount -gt 0) { throw "-SelectExistingImages不可與明確image參數同時使用。" }
    Write-Section "選擇既有本機 Docker images（進階模式）"
    $localImages = Get-LocalDockerImages
    $selectedImages = Read-MultipleSelection -Items $localImages -Prompt "輸入要 push 的項次，可用空格複選" -Formatter {
        param($item)
        "$($item.Reference) | ID=$($item.Id) | $($item.Size) | $($item.CreatedSince)"
    }
    foreach ($image in $selectedImages) {
        while ($true) {
            $role = Get-RoleChoice -ImageReference $image.Reference
            if (($role -eq "push-only") -or $usedRoles.Add($role)) { break }
            Write-Warning "用途 '$role' 已由另一個 image使用；每次執行每個部署用途只能選一個image。"
        }
        $defaultAlias = Get-DefaultAliasForRole -Role $role -LocalRepository $image.Repository
        $alias = Read-RequiredValue -Prompt "GCP image alias（$($image.Reference)）" -Default $defaultAlias `
            -Validator { param($value) ($value.Length -le 128) -and ($value -match '^[a-z0-9]+(?:[._-][a-z0-9]+)*$') } `
            -ValidationMessage "alias不得超過128字元，只能使用小寫英數字及 . _ -，且開頭與結尾必須是英數字。"
        $shortId = ($image.Id -replace '^sha256:', '')
        if ($shortId.Length -gt 12) { $shortId = $shortId.Substring(0, 12) }
        $defaultTag = "compat-$((Get-Date).ToString('yyyyMMdd-HHmmss'))-$shortId"
        while ($true) {
            $tag = Read-RequiredValue -Prompt "不可變版本 tag（$($image.Reference)）" -Default $defaultTag `
                -Validator { param($value) $value -match '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$' } `
                -ValidationMessage "tag格式無效或超過128字元。"
            $remoteReference = "$registryRoot/$alias`:$tag"
            if (-not (Test-RemoteTagExists -RemoteReference $remoteReference)) { break }
            Write-Warning "遠端tag已存在：$remoteReference。immutable tag不可覆蓋，請輸入新tag。"
            $defaultTag = "compat-$((Get-Date).ToString('yyyyMMdd-HHmmss'))-$shortId-2"
        }
        $plans.Add([pscustomobject]@{
            LocalReference = $image.Reference; Alias = $alias; Tag = $tag
            RemoteReference = $remoteReference; DigestReference = $null; Role = $role
        })
    }
}
else {
    if ($providedImageCount -eq 0) {
        Write-Section "從Dockerfile自動build並完成本機image驗收"
        $builder = Join-Path $PSScriptRoot "build_and_validate_cloud_run_compat_images.ps1"
        if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) { throw "找不到image builder：$builder" }
        $built = & $builder -DryRun:$DryRun | Select-Object -Last 1
        if ($null -eq $built) { throw "image builder未回傳建置結果。" }
        $ApiImage = [string]$built.Api
        $UiImage = [string]$built.Ui
        $RuntimeOpsImage = [string]$built.RuntimeOps
    }
    $roleImages = [ordered]@{ api = $ApiImage; ui = $UiImage; "runtime-ops" = $RuntimeOpsImage }
    $head = ((& $script:Git -C (Resolve-Path (Join-Path $PSScriptRoot "..\..")) rev-parse --short=12 HEAD) -join "").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($head)) { throw "無法取得Git HEAD。" }
    $baseTag = "compat-$((Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss'))-$head"
    foreach ($role in $Roles) {
        $localReference = [string]$roleImages[$role]
        if ([string]::IsNullOrWhiteSpace($localReference)) { throw "角色'$role'缺少本機image reference。" }
        if (-not $DryRun) {
            & $script:Docker image inspect $localReference *> $null
            if ($LASTEXITCODE -ne 0) { throw "找不到已通過驗收的本機image：$localReference" }
        }
        $alias = Get-DefaultAliasForRole -Role $role -LocalRepository $localReference.Split(':')[0]
        $tag = $baseTag
        $suffix = 1
        while (Test-RemoteTagExists -RemoteReference "$registryRoot/$alias`:$tag") {
            $suffix++
            $tag = "$baseTag-$suffix"
        }
        $plans.Add([pscustomobject]@{
            LocalReference = $localReference; Alias = $alias; Tag = $tag
            RemoteReference = "$registryRoot/$alias`:$tag"; DigestReference = $null; Role = $role
        })
    }
}

$plannedRoles = @($plans | Where-Object { $_.Role -ne "push-only" } | ForEach-Object { $_.Role })
if ($InitialProvision) {
    $missingRoles = @(@("api", "ui", "runtime-ops") | Where-Object { $_ -notin $plannedRoles })
    if ($missingRoles.Count -gt 0) {
        throw "首次部署必須同時選擇 API、UI、runtime-ops 三個 images；缺少：$($missingRoles -join ', ')。尚未push任何image。"
    }
}
if (-not $InitialProvision) {
    $requiredResources = @()
    if ($plannedRoles -contains "api") { $requiredResources += [pscustomobject]@{ Kind = "services"; Name = "union-api-compat" } }
    if ($plannedRoles -contains "ui") { $requiredResources += [pscustomobject]@{ Kind = "services"; Name = "union-ui-compat" } }
    if ($plannedRoles -contains "runtime-ops") {
        foreach ($name in @("union-durable-compat", "union-line-compat", "union-incident-compat")) {
            $requiredResources += [pscustomobject]@{ Kind = "worker-pools"; Name = $name }
        }
        $requiredResources += [pscustomobject]@{ Kind = "jobs"; Name = "union-monitor-compat" }
    }
    foreach ($resource in $requiredResources) {
        if (-not (Test-GcloudResource -Arguments @(
            "run", $resource.Kind, "describe", $resource.Name, "--project=$ProjectId", "--region=$Region"
        ))) {
            throw "缺少既有 Cloud Run $($resource.Kind) '$($resource.Name)'；更新腳本禁止建立資源，尚未push任何image。"
        }
    }
}
$needsExistingApi = (($plannedRoles -contains "ui") -or ($plannedRoles -contains "runtime-ops")) -and (-not ($plannedRoles -contains "api"))
if ($needsExistingApi) {
    $apiExists = (-not ($AssumeNewProject -and $DryRun)) -and (Test-GcloudResource -Arguments @(
        "run", "services", "describe", "union-api-compat", "--project=$ProjectId", "--region=$Region"
    ))
    if (-not $apiExists) {
        throw "選擇了UI／runtime-ops，但Project內沒有union-api-compat。首次部署必須同時選擇API image。"
    }
}
if ($plannedRoles -contains "api") { Assert-ServiceAccountExists -AccountId "union-api-compat" }
if ($plannedRoles -contains "ui") { Assert-ServiceAccountExists -AccountId "union-ui-compat" }
if ($plannedRoles -contains "runtime-ops") {
    @("union-durable-compat", "union-line-compat", "union-incident-compat", "union-monitor-compat") |
        ForEach-Object { Assert-ServiceAccountExists -AccountId $_ }
}

Write-Section "Push 計畫"
foreach ($plan in $plans) {
    Write-Host ("{0} -> {1} | role={2}" -f $plan.LocalReference, $plan.RemoteReference, $plan.Role)
}
if (-not (Read-ConfirmationToken -Prompt "確認以上 image 將新增 tag 並 push 到 GCP" -Expected "PUSH")) {
    throw "使用者取消 push。"
}

Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
    "auth", "configure-docker", "$Region-docker.pkg.dev", "--quiet"
)
foreach ($plan in $plans) {
    Invoke-NativeMutation -Executable $script:Docker -Arguments @("tag", $plan.LocalReference, $plan.RemoteReference)
    Invoke-NativeMutation -Executable $script:Docker -Arguments @("push", $plan.RemoteReference)
    $plan.DigestReference = Resolve-RemoteDigestReference -RemoteReference $plan.RemoteReference
    Write-Host "digest: $($plan.DigestReference)"
}

$deployPlans = @($plans | Where-Object { $_.Role -ne "push-only" })
if ($deployPlans.Count -eq 0) {
    Write-Host "所有選取 images 都設定為只 push；未更新 Cloud Run。"
    exit 0
}

Show-CloudRunResources
Write-Section "Cloud Run 部署計畫"
foreach ($plan in $deployPlans) {
    Write-Host ("role={0} | {1}" -f $plan.Role, $plan.DigestReference)
}
Write-Warning "這是開發用 compat/staging 部署；嚴禁正式部署，不會執行 migration、production traffic cutover 或建立 VPN。"
if (-not (Read-ConfirmationToken -Prompt "確認部署／更新以上 Cloud Run 測試資源" -Expected "DEPLOY")) {
    Write-Warning "images 已 push，但使用者取消 Cloud Run 部署。"
    exit 0
}

$apiPlan = $deployPlans | Where-Object { $_.Role -eq "api" } | Select-Object -First 1
if ($null -ne $apiPlan) {
    Deploy-ApiImage -DigestReference $apiPlan.DigestReference
}
$needsApi = @($deployPlans | Where-Object { $_.Role -in @("ui", "runtime-ops") }).Count -gt 0
if ($needsApi -and ($null -eq $apiPlan) -and (-not ($AssumeNewProject -and $DryRun))) {
    if (-not (Test-GcloudResource -Arguments @(
        "run", "services", "describe", "union-api-compat", "--project=$ProjectId", "--region=$Region"
    ))) {
        throw "選擇了 UI／runtime-ops，但 Project 內沒有 union-api-compat，且本次未選 API image。"
    }
}
$apiUrl = $null
if ($needsApi -or ($null -ne $apiPlan)) {
    $apiUrl = Get-ApiUrl
    Complete-InitialApiConfiguration -ApiUrl $apiUrl
}
$uiPlan = $deployPlans | Where-Object { $_.Role -eq "ui" } | Select-Object -First 1
if ($null -ne $uiPlan) {
    Deploy-UiImage -DigestReference $uiPlan.DigestReference -ApiUrl $apiUrl
}
$runtimePlan = $deployPlans | Where-Object { $_.Role -eq "runtime-ops" } | Select-Object -First 1
if ($null -ne $runtimePlan) {
    Deploy-RuntimeOpsImage -DigestReference $runtimePlan.DigestReference -ApiUrl $apiUrl
}

$uiUrl = $null
if ($InitialProvision -and (-not $DryRun)) {
    $uiUrl = ((Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "run", "services", "describe", "union-ui-compat", "--project=$ProjectId", "--region=$Region", "--format=value(status.url)"
    )).Output -join "").Trim()
    if (($null -ne $runtimePlan) -and (-not [string]::IsNullOrWhiteSpace($uiUrl))) {
        Complete-InitialMonitorConfiguration -ApiUrl $apiUrl -UiUrl $uiUrl
    }
}

Write-Section "完成"
Write-Host "Project: $ProjectId"
Write-Host "Artifact Registry: $registryRoot"
Write-Host "已部署的 image 一律使用 digest reference。"
if ($InitialProvision) {
    $uiUrl = if ($DryRun) {
        "https://union-ui-compat-<generated>.$Region.run.app"
    }
    elseif ([string]::IsNullOrWhiteSpace($uiUrl)) {
        ((Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
            "run", "services", "describe", "union-ui-compat", "--project=$ProjectId", "--region=$Region", "--format=value(status.url)"
        )).Output -join "").Trim()
    }
    else { $uiUrl }
    Write-Host "Admin UI: $uiUrl"
    Write-Host "LINE Webhook URL: $apiUrl/webhook/line"
    Write-Host "LIFF Endpoint URL: $apiUrl/liff-page"
    Write-Host "LINE Developers Console: https://developers.line.biz/console/"
    Write-Host "Webhook official guide: https://developers.line.biz/en/docs/messaging-api/verify-webhook-url/"
    Write-Host "LIFF official guide: https://developers.line.biz/en/docs/liff/registering-liff-apps/"
}
Write-Warning "仍須由首次腳本驗證 API/UI、OIDC、DB bridge、Webhook與LIFF；未通過不得宣稱完成。"
