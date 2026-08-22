#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$Region = "asia-east1",
    [string]$Zone = "asia-east1-b",
    [switch]$PreflightOnly,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# DEVELOPMENT ONLY: GCE + IAP reverse SSH Tunnel edition.
# FORBIDDEN FOR PRODUCTION. The approved production route remains Cloud VPN -> NAS.

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
    if ($null -eq $command) {
        $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($null -eq $command) {
        throw "找不到必要工具 '$Name'。請先安裝並確認它位於 PATH。"
    }
    return $command.Source
}

function Assert-Prerequisites {
    $failures = [System.Collections.Generic.List[string]]::new()
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        $failures.Add("需要PowerShell 7以上；請使用pwsh執行，不要使用Windows PowerShell 5.1。")
    }
    foreach ($name in @("git", "docker", "gcloud", "ssh.exe", "ssh-keygen.exe", "icacls.exe")) {
        $command = if ($name -eq "gcloud") {
            Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
        }
        else { $null }
        if ($null -eq $command) { $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1 }
        if ($null -eq $command) { $failures.Add("缺少工具'$name'；請安裝並加入PATH。") }
    }
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    foreach ($relativePath in @(
        "pyproject.toml", "uv.lock", ".env",
        "docker/compat/Dockerfile.api", "docker/compat/Dockerfile.ui", "docker/compat/Dockerfile.runtime-ops",
        "scripts/launchers/build_and_validate_cloud_run_compat_images.ps1",
        "scripts/launchers/publish_gcp_cloud_run_compat.ps1",
        "scripts/launchers/manage_gcp_cloud_run_db_bridge.ps1"
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
        throw "部署前置檢查失敗：`n$($numbered -join "`n")"
    }
    Write-Host "[PASS] prerequisites：PowerShell、Git、Docker、gcloud、OpenSSH、ACL工具及專案檔案。" -ForegroundColor Green
}

function Get-LocalEnvironment {
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $path = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "找不到本機 .env；首次開發部署只讀取既有 Git-ignored 設定，不會把它封裝進 image。"
    }
    $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
    try { $content = $strictUtf8.GetString([System.IO.File]::ReadAllBytes($path)) }
    catch { throw "本機.env不是合法strict UTF-8：$($_.Exception.Message)" }
    $values = @{}
    foreach ($line in ($content -split "`r?`n")) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $value = $line.Split('=', 2)
        $values[$key.Trim()] = $value.Trim()
    }
    return $values
}

function Get-RequiredLocalValue {
    param([hashtable]$Values, [string]$Name)
    $value = [string]$Values[$Name]
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '^your_.+_here$') {
        throw "本機 .env 缺少有效的 $Name。"
    }
    return $value
}

function Invoke-GcloudWithStandardInput {
    param([string[]]$Arguments, [string]$Value)
    $display = Format-Command -Executable $script:Gcloud -Arguments $Arguments
    if ($DryRun) {
        Write-Host "[DRY-RUN] $display < redacted-stdin" -ForegroundColor Yellow
        return
    }
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $script:Gcloud
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardInput = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        foreach ($argument in $Arguments) { $null = $startInfo.ArgumentList.Add($argument) }
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        $null = $process.Start()
        $process.StandardInput.Write($Value)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $retryable = $stderr -match '(?i)(HTTP\s*429|RESOURCE_EXHAUSTED|rateLimitExceeded|too many requests|service.+not enabled|has not been used.+before|propagation|please retry)'
        if (($process.ExitCode -eq 0) -or (-not $retryable) -or ($attempt -eq 6)) { break }
        $delay = [Math]::Min(30, [Math]::Pow(2, $attempt)) + (Get-Random -Minimum 0 -Maximum 3)
        Write-Warning "GCP暫時性錯誤；$delay 秒後重試（$attempt/6）。"
        Start-Sleep -Seconds $delay
    }
    if ($process.ExitCode -ne 0) { throw "命令失敗（exit=$($process.ExitCode)）：$display`n$stderr" }
    if (-not [string]::IsNullOrWhiteSpace($stdout)) { Write-Host $stdout.Trim() }
}

function Ensure-Secret {
    param([string]$Name, [string]$Value, [string]$TargetProjectId, [switch]$AssumeAbsent)
    $exists = (-not $AssumeAbsent) -and (Test-GcloudResource -Arguments @(
        "secrets", "describe", $Name, "--project=$TargetProjectId"
    ))
    if (-not $exists) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "secrets", "create", $Name, "--project=$TargetProjectId", "--replication-policy=automatic",
            "--labels=environment=staging,deployment=compat,bridge=gce-iap-reverse-ssh"
        )
        Invoke-GcloudWithStandardInput -Arguments @(
            "secrets", "versions", "add", $Name, "--project=$TargetProjectId", "--data-file=-"
        ) -Value $Value
    }
    else {
        Write-Host "Secret '$Name' 已存在；首次設定不覆寫既有版本。"
    }
}

function Ensure-ProjectRole {
    param([string]$TargetProjectId, [string]$Member, [string]$Role)
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "projects", "add-iam-policy-binding", $TargetProjectId, "--member=$Member", "--role=$Role", "--quiet"
    )
}

function Ensure-DevelopmentBridge {
    param([string]$TargetProjectId, [string]$TargetRegion, [string]$TargetZone, [string]$SubnetCidr, [switch]$AssumeAbsent)
    Write-Section "建立開發用 GCE＋IAP 反向 SSH DB bridge（嚴禁正式部署）"
    if ($AssumeAbsent -or (-not (Test-GcloudResource -Arguments @(
        "compute", "firewall-rules", "describe", "allow-iap-ssh-db-bridge", "--project=$TargetProjectId"
    )))) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "compute", "firewall-rules", "create", "allow-iap-ssh-db-bridge", "--project=$TargetProjectId",
            "--network=union-compat-vpc", "--direction=INGRESS", "--action=ALLOW", "--rules=tcp:22",
            "--source-ranges=35.235.240.0/20", "--target-tags=union-db-bridge-compat"
        )
    }
    if ($AssumeAbsent -or (-not (Test-GcloudResource -Arguments @(
        "compute", "firewall-rules", "describe", "allow-cloud-run-db-bridge", "--project=$TargetProjectId"
    )))) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "compute", "firewall-rules", "create", "allow-cloud-run-db-bridge", "--project=$TargetProjectId",
            "--network=union-compat-vpc", "--direction=INGRESS", "--action=ALLOW", "--rules=tcp:13306",
            "--source-ranges=$SubnetCidr", "--target-tags=union-db-bridge-compat"
        )
    }
    if ($AssumeAbsent -or (-not (Test-GcloudResource -Arguments @(
        "compute", "instances", "describe", "union-db-bridge-compat", "--project=$TargetProjectId", "--zone=$TargetZone"
    )))) {
        $startupScript = "#!/bin/bash`nset -euo pipefail`nsed -ri 's/^#?GatewayPorts .*/GatewayPorts clientspecified/' /etc/ssh/sshd_config`nsystemctl restart ssh || systemctl restart sshd`n"
        $startupPath = Join-Path ([System.IO.Path]::GetTempPath()) ("union-db-bridge-" + [guid]::NewGuid().ToString("N") + ".sh")
        try {
            [System.IO.File]::WriteAllText($startupPath, $startupScript, [System.Text.UTF8Encoding]::new($false))
            Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
                "compute", "instances", "create", "union-db-bridge-compat", "--project=$TargetProjectId", "--zone=$TargetZone",
                "--machine-type=e2-micro", "--network-interface=network=union-compat-vpc,subnet=union-compat-run,no-address",
                "--tags=union-db-bridge-compat", "--labels=environment=staging,deployment=compat,usage=development-db-bridge",
                "--metadata=enable-oslogin=TRUE", "--metadata-from-file=startup-script=$startupPath", "--image-family=debian-12", "--image-project=debian-cloud",
                "--boot-disk-size=10GB", "--boot-disk-type=pd-standard", "--quiet"
            )
        }
        finally {
            if (Test-Path -LiteralPath $startupPath) { Remove-Item -LiteralPath $startupPath -Force }
        }
    }
    if ($DryRun -and $AssumeAbsent) { return "10.20.0.2" }
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "compute", "instances", "describe", "union-db-bridge-compat", "--project=$TargetProjectId", "--zone=$TargetZone",
        "--format=value(networkInterfaces[0].networkIP)"
    )
    $address = (($result.Output -join "").Trim())
    if ($address -notmatch '^\d{1,3}(?:\.\d{1,3}){3}$') { throw "無法取得 DB bridge VM 私有 IP。" }
    return $address
}

function Assert-HttpEndpoint {
    param([string]$Name, [string]$Url)
    if ($DryRun) {
        Write-Host "[DRY-RUN] HTTP acceptance: $Name -> $Url"
        return
    }
    $lastError = $null
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 15 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "PASS $Name ($($response.StatusCode))" -ForegroundColor Green
                return
            }
        }
        catch { $lastError = $_ }
        Start-Sleep -Seconds 5
    }
    throw "HTTP驗收失敗：$Name -> $Url；$lastError"
}

function Format-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $displayArgs = foreach ($argument in $Arguments) {
        if ($argument -match '\s') { '"{0}"' -f ($argument -replace '"', '\"') }
        else { $argument }
    }
    return ((Split-Path -Leaf $Executable) + " " + ($displayArgs -join " "))
}

function Invoke-NativeRead {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $maxAttempts = if ((Split-Path -Leaf $Executable) -match '^gcloud(?:\.cmd)?$') { 6 } else { 1 }
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
        $retryable = $detail -match '(?i)(HTTP\s*429|RESOURCE_EXHAUSTED|rateLimitExceeded|too many requests|service.+not enabled|has not been used.+before|propagation|please retry)'
        if (($exitCode -eq 0) -or (-not $retryable) -or ($attempt -eq $maxAttempts)) { break }
        $delay = [Math]::Min(30, [Math]::Pow(2, $attempt)) + (Get-Random -Minimum 0 -Maximum 3)
        Write-Warning "GCP暫時性錯誤；$delay 秒後重試（$attempt/$maxAttempts）。"
        Start-Sleep -Seconds $delay
    }
    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        throw "命令失敗（exit=$exitCode）：$(Format-Command -Executable $Executable -Arguments $Arguments)`n$detail"
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
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
    $maxAttempts = if ((Split-Path -Leaf $Executable) -match '^gcloud(?:\.cmd)?$') { 6 } else { 1 }
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $nativeOutput = @(& $Executable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        $detail = ($nativeOutput | ForEach-Object { [string]$_ }) -join "`n"
        $retryable = $detail -match '(?i)(HTTP\s*429|RESOURCE_EXHAUSTED|rateLimitExceeded|too many requests|service.+not enabled|has not been used.+before|propagation|please retry)'
        if (($exitCode -eq 0) -or (-not $retryable) -or ($attempt -eq $maxAttempts)) { break }
        $delay = [Math]::Min(30, [Math]::Pow(2, $attempt)) + (Get-Random -Minimum 0 -Maximum 3)
        Write-Warning "GCP暫時性錯誤；$delay 秒後重試（$attempt/$maxAttempts）。"
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
    if ([string]::IsNullOrWhiteSpace($text)) { return @() }
    return @($text | ConvertFrom-Json)
}

function Test-GcloudResource {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $script:Gcloud @Arguments *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-EnabledApis {
    param([Parameter(Mandatory = $true)][string]$TargetProjectId, [Parameter(Mandatory = $true)][string[]]$Services)
    if ($DryRun) {
        Write-Host "[DRY-RUN] 等待必要GCP APIs完成propagation。" -ForegroundColor Yellow
        return
    }
    $deadline = (Get-Date).AddMinutes(8)
    do {
        $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
            "services", "list", "--enabled", "--project=$TargetProjectId", "--format=value(config.name)"
        )
        $enabled = @($result.Output | ForEach-Object { [string]$_ })
        $missing = @($Services | Where-Object { $_ -notin $enabled })
        if ($missing.Count -eq 0) {
            Write-Host "[PASS] 必要GCP APIs已啟用並可查詢。" -ForegroundColor Green
            return
        }
        Write-Warning "等待API propagation：$($missing -join ', ')"
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)
    throw "GCP APIs在8分鐘內未完成propagation：$($missing -join ', ')"
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
        if (-not [string]::IsNullOrWhiteSpace($Default)) { $suffix = " [$Default]" }
        $value = (Read-Host "$Prompt$suffix").Trim()
        if ([string]::IsNullOrWhiteSpace($value)) { $value = $Default }
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

function Read-ConfirmationToken {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    if ($DryRun) { return $true }
    $actual = (Read-Host "$Prompt（輸入 $Expected）").Trim()
    return $actual -ceq $Expected
}

function Get-OpenBillingAccounts {
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "billing", "accounts", "list", "--filter=open=true", "--format=json"
    )
    return @(ConvertFrom-JsonOutput -Output $result.Output)
}

function Select-BillingAccount {
    while ($true) {
        $accounts = Get-OpenBillingAccounts
        Write-Section "選擇 Billing Account"
        for ($index = 0; $index -lt $accounts.Count; $index++) {
            $accountId = ([string]$accounts[$index].name).Split('/')[-1]
            $currency = "currency unknown"
            if ($accounts[$index].PSObject.Properties["currencyCode"] -and (-not [string]::IsNullOrWhiteSpace([string]$accounts[$index].currencyCode))) {
                $currency = [string]$accounts[$index].currencyCode
            }
            Write-Host ("[{0}] {1} — {2} — {3}" -f ($index + 1), $accountId, $accounts[$index].displayName, $currency)
        }
        $newIndex = $accounts.Count + 1
        Write-Host "[$newIndex] 建立新的 Billing Account（需開啟瀏覽器人工完成付款資料）"
        $raw = (Read-Host "輸入 Billing Account 項次").Trim()
        $number = 0
        if (-not [int]::TryParse($raw, [ref]$number)) {
            Write-Warning "請輸入有效項次。"
            continue
        }
        if (($number -ge 1) -and ($number -le $accounts.Count)) {
            return ([string]$accounts[$number - 1].name).Split('/')[-1]
        }
        if ($number -eq $newIndex) {
            if ($DryRun) {
                Write-Host "[DRY-RUN] 將開啟 https://console.cloud.google.com/billing/create，完成後重新查詢。" -ForegroundColor Yellow
                return "<NEW-BILLING-ACCOUNT-ID>"
            }
            Write-Warning "Billing Account 的付款方式與法律資料無法由 gcloud 自動建立。"
            Start-Process "https://console.cloud.google.com/billing/create"
            Read-Host "請在瀏覽器完成建立後，回到此視窗按 Enter 重新查詢"
            continue
        }
        Write-Warning "請輸入 1 到 $newIndex 之間的項次。"
    }
}

function Get-BillingCurrency {
    param([Parameter(Mandatory = $true)][string]$BillingAccountId)
    if ($BillingAccountId -eq "<NEW-BILLING-ACCOUNT-ID>") {
        return Read-RequiredValue -Prompt "新Billing Account計費幣別（ISO 4217，例如TWD或USD）" -Default "TWD" `
            -Validator { param($value) $value -match '^[A-Z]{3}$' } `
            -ValidationMessage "請輸入3碼大寫ISO 4217幣別，例如TWD或USD。"
    }
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "billing", "accounts", "describe", $BillingAccountId, "--format=value(currencyCode)"
    ) -AllowFailure
    if ($result.ExitCode -eq 0) {
        $currency = (($result.Output -join "").Trim()).ToUpperInvariant()
        if ($currency -match '^[A-Z]{3}$') {
            Write-Host "已自動偵測Billing Account計費幣別：$currency"
            return $currency
        }
    }
    Write-Warning "無法從Billing Account API讀取currencyCode；可能是權限不足或舊版gcloud輸出不含該欄位。"
    return Read-RequiredValue -Prompt "請確認Billing Account計費幣別（ISO 4217，例如TWD或USD）" -Default "TWD" `
        -Validator { param($value) $value -match '^[A-Z]{3}$' } `
        -ValidationMessage "請輸入3碼大寫ISO 4217幣別，例如TWD或USD。"
}

function Assert-ExistingProjectIsCompatibilityProject {
    param([Parameter(Mandatory = $true)][string]$TargetProjectId)
    $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "projects", "describe", $TargetProjectId, "--format=json"
    )
    $project = (ConvertFrom-JsonOutput -Output $result.Output)[0]
    $environment = ""
    $deployment = ""
    if ($null -ne $project.labels) {
        if ($project.labels.PSObject.Properties["environment"]) { $environment = [string]$project.labels.environment }
        if ($project.labels.PSObject.Properties["deployment"]) { $deployment = [string]$project.labels.deployment }
    }
    if (($environment -notin @("staging", "test")) -or ($deployment -ne "compat")) {
        throw "Project '$TargetProjectId' 已存在，但不是本腳本建立的 compat staging Project；為避免誤改其他環境，腳本已停止。"
    }
    if (-not (Read-ConfirmationToken -Prompt "Project 已存在；確認要從中斷處繼續初始化" -Expected "RESUME")) {
        throw "使用者取消。"
    }
}

function Ensure-ServiceAccount {
    param(
        [Parameter(Mandatory = $true)][string]$AccountId,
        [Parameter(Mandatory = $true)][string]$DisplayName,
        [Parameter(Mandatory = $true)][string]$TargetProjectId,
        [switch]$AssumeAbsent
    )
    $email = "$AccountId@$TargetProjectId.iam.gserviceaccount.com"
    $exists = (-not $AssumeAbsent) -and (Test-GcloudResource -Arguments @(
        "iam", "service-accounts", "describe", $email, "--project=$TargetProjectId"
    ))
    if (-not $exists) {
        Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
            "iam", "service-accounts", "create", $AccountId,
            "--project=$TargetProjectId", "--display-name=$DisplayName"
        )
    }
}

function Select-OrCreateRepository {
    param(
        [Parameter(Mandatory = $true)][string]$TargetProjectId,
        [Parameter(Mandatory = $true)][string]$TargetRegion,
        [switch]$AssumeNoRepositories
    )
    $repositories = @()
    if (-not $AssumeNoRepositories) {
        $result = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
            "artifacts", "repositories", "list", "--project=$TargetProjectId",
            "--location=$TargetRegion", "--format=json"
        )
        $repositories = @(ConvertFrom-JsonOutput -Output $result.Output | Where-Object { $_.format -eq "DOCKER" })
    }
    Write-Section "選擇或建立 Artifact Registry"
    for ($index = 0; $index -lt $repositories.Count; $index++) {
        $name = ([string]$repositories[$index].name).Split('/')[-1]
        $immutable = "mutable-tags"
        if ($repositories[$index].PSObject.Properties["dockerConfig"] -and $repositories[$index].dockerConfig.immutableTags) {
            $immutable = "immutable-tags"
        }
        Write-Host ("[{0}] {1} — {2}" -f ($index + 1), $name, $immutable)
    }
    $createIndex = $repositories.Count + 1
    Write-Host "[$createIndex] 建立新的 Docker 倉庫"
    while ($true) {
        $raw = (Read-Host "輸入倉庫項次").Trim()
        $number = 0
        if ([int]::TryParse($raw, [ref]$number)) {
            if (($number -ge 1) -and ($number -le $repositories.Count)) {
                $selected = $repositories[$number - 1]
                if (-not ($selected.PSObject.Properties["dockerConfig"] -and $selected.dockerConfig.immutableTags)) {
                    throw "選取的倉庫未啟用 immutable tags；compat部署要求不可變tag，請建立新倉庫。"
                }
                return ([string]$selected.name).Split('/')[-1]
            }
            if ($number -eq $createIndex) { break }
        }
        Write-Warning "請輸入 1 到 $createIndex 之間的項次。"
    }
    $repositoryName = Read-RequiredValue -Prompt "新倉庫名稱" -Default "labor-union-compat" `
        -Validator { param($value) $value -match '^[a-z][a-z0-9._-]{1,61}[a-z0-9]$' } `
        -ValidationMessage "倉庫名稱需3～63字元，以小寫字母開頭、英數字結尾，只能使用小寫英數字及 . _ -。"
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "artifacts", "repositories", "create", $repositoryName,
        "--project=$TargetProjectId", "--location=$TargetRegion",
        "--repository-format=docker", "--immutable-tags",
        "--description=Labor Union isolated Cloud Run compatibility images"
    )
    return $repositoryName
}

Write-Section "prerequisites集中預檢"
Assert-Prerequisites

Write-Section "工具與登入檢查"
$script:Gcloud = Resolve-Executable -Name "gcloud"
$script:Docker = Resolve-Executable -Name "docker"
Write-Host "gcloud: $script:Gcloud"
Write-Host "docker: $script:Docker"

$dockerResult = Invoke-NativeRead -Executable $script:Docker -Arguments @("info", "--format", "{{.ServerVersion}}") -AllowFailure
if ($dockerResult.ExitCode -ne 0) {
    throw "Docker daemon 無法使用。請先啟動 Docker Desktop。"
}

$activeAccountResult = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
    "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"
) -AllowFailure
$activeAccount = ""
if ($activeAccountResult.Output.Count -gt 0) {
    $activeAccount = [string]($activeAccountResult.Output | Select-Object -First 1)
}
if ([string]::IsNullOrWhiteSpace($activeAccount)) {
    if ($DryRun -or $PreflightOnly) {
        throw "目前沒有gcloud active account。DryRun／PreflightOnly不會開啟登入；請先執行gcloud auth login。"
    }
    Write-Warning "即將開啟瀏覽器，登入與 MFA 必須由使用者人工完成。"
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @("auth", "login")
    $activeAccountResult = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"
    )
    $activeAccount = [string]($activeAccountResult.Output | Select-Object -First 1)
}
Write-Host "Active account: $activeAccount"

$localEnvironment = Get-LocalEnvironment
$dbUser = Get-RequiredLocalValue -Values $localEnvironment -Name "DB_USER"
$dbPassword = Get-RequiredLocalValue -Values $localEnvironment -Name "DB_PASSWORD"
$dbDatabase = Get-RequiredLocalValue -Values $localEnvironment -Name "DB_DATABASE"
$mysqlContainerPortText = Get-RequiredLocalValue -Values $localEnvironment -Name "DB_PORT"
$mysqlContainerPort = 0
if ((-not [int]::TryParse($mysqlContainerPortText, [ref]$mysqlContainerPort)) -or $mysqlContainerPort -lt 1 -or $mysqlContainerPort -gt 65535) {
    throw "本機 .env 的 DB_PORT 無效。"
}
$mysqlContainer = [string]$localEnvironment["MYSQL_CONTAINER"]
if ([string]::IsNullOrWhiteSpace($mysqlContainer)) { $mysqlContainer = "mysql_db" }
$totpKeyring = Get-RequiredLocalValue -Values $localEnvironment -Name "ACCESS_CONTROL_TOTP_KEYRING"
$lineChannelSecret = Get-RequiredLocalValue -Values $localEnvironment -Name "LINE_CHANNEL_SECRET"
$lineAccessToken = Get-RequiredLocalValue -Values $localEnvironment -Name "LINE_CHANNEL_ACCESS_TOKEN"
$lineLiffId = Get-RequiredLocalValue -Values $localEnvironment -Name "LINE_LIFF_ID"
$lineLoginChannelId = Get-RequiredLocalValue -Values $localEnvironment -Name "LINE_LOGIN_CHANNEL_ID"

if ($PreflightOnly) {
    Write-Host "[PASS] .env必要值格式與登入狀態已通過；未建立image、未修改GCP、未啟動Tunnel。" -ForegroundColor Green
    exit 0
}

$billingAccount = Select-BillingAccount
$billingCurrency = Get-BillingCurrency -BillingAccountId $billingAccount

Write-Section "Project 設定"
$projectId = Read-RequiredValue -Prompt "Project ID（建立後不可修改，且全球唯一）" -Default "" `
    -Validator { param($value) $value -match '^[a-z][a-z0-9-]{4,28}[a-z0-9]$' } `
    -ValidationMessage "Project ID需6～30字元，以小寫字母開頭、英數字結尾，只能包含小寫英數字與連字號。"
$projectName = Read-RequiredValue -Prompt "Project顯示名稱" -Default "Labor Union Compatibility"
$defaultBudgetValue = "100"
if ($billingCurrency -eq "TWD") { $defaultBudgetValue = "3000" }
$budgetValue = Read-RequiredValue -Prompt "每月預算金額（計費幣別：$billingCurrency）" -Default $defaultBudgetValue `
    -Validator { param($value) $value -match '^\d+(?:\.\d{1,2})?$' } `
    -ValidationMessage "只需輸入正數金額，例如3000或100.50；幣別已由Billing Account自動決定。"
$budgetAmount = "$budgetValue$billingCurrency"
$subnetCidr = Read-RequiredValue -Prompt "Cloud Run測試subnet CIDR（必須與地端網段不重疊）" -Default "10.20.0.0/24" `
    -Validator { param($value) $value -match '^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$' } `
    -ValidationMessage "請輸入IPv4 CIDR，例如10.20.0.0/24。"

Write-Host ""
Write-Host "Account:  $activeAccount"
Write-Host "Billing:  $billingAccount"
Write-Host "Currency: $billingCurrency"
Write-Host "Project:  $projectId — $projectName"
Write-Host "Region:   $Region"
Write-Host "Budget:   $budgetAmount / month"
Write-Host "Subnet:   $subnetCidr"
Write-Host "DB bridge: GCE private VM -> IAP reverse SSH -> localhost-only forward -> $mysqlContainer`:$mysqlContainerPort"
Write-Warning "開發用 GCE＋IAP反向SSH Tunnel版，嚴禁正式部署。這會建立可能產生費用的 staging/compat 資源，且會讓Cloud Run測試API連到目前本機DB；不會建立VPN或執行migration。"
if ($dbUser -ieq "root") {
    Write-Warning "目前DB_USER=root；只允許短期開發相容性測試，正式部署前必須改用獨立最小權限application user並輪替secret。"
}
Write-Warning "三個runtime worker建立後會執行目前DB中的durable／LINE／incident工作；LINE設定也會指向目前.env指定的channel。只允許非production資料與測試LINE channel。"
if (-not (Read-ConfirmationToken -Prompt "確認目前DB為可供Cloud Run開發測試的非production DB，且LINE channel允許測試外部副作用" -Expected "DEV-SAFE")) {
    throw "DB／LINE開發測試安全邊界未確認，停止建立。"
}
if (-not (Read-ConfirmationToken -Prompt "確認以上首次環境設定" -Expected "CREATE")) {
    throw "使用者取消建立。"
}

Write-Section "從Dockerfile自動build並完成本機image驗收"
$builder = Join-Path $PSScriptRoot "build_and_validate_cloud_run_compat_images.ps1"
$builtImages = & $builder -EnvFile (Join-Path ((Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path) ".env") -DryRun:$DryRun | Select-Object -Last 1
if ($null -eq $builtImages) { throw "image builder未回傳三個驗收通過的images。" }

$projectExists = Test-GcloudResource -Arguments @("projects", "describe", $projectId)
if ($projectExists) {
    Assert-ExistingProjectIsCompatibilityProject -TargetProjectId $projectId
}
else {
    Write-Host "Project父層可留空；公司環境通常應指定organization或folder。"
    $parentType = (Read-Host "父層類型 [none/organization/folder]（預設none）").Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($parentType)) { $parentType = "none" }
    $createArgs = @(
        "projects", "create", $projectId, "--name=$projectName",
        "--labels=environment=staging,system=labor-union,deployment=compat"
    )
    if ($parentType -eq "organization") {
        $parentId = Read-RequiredValue -Prompt "Organization ID" -Default "" -Validator { param($value) $value -match '^\d+$' }
        $createArgs += "--organization=$parentId"
    }
    elseif ($parentType -eq "folder") {
        $parentId = Read-RequiredValue -Prompt "Folder ID" -Default "" -Validator { param($value) $value -match '^\d+$' }
        $createArgs += "--folder=$parentId"
    }
    elseif ($parentType -ne "none") {
        throw "不支援的父層類型 '$parentType'。"
    }
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments $createArgs
}

Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
    "billing", "projects", "link", $projectId, "--billing-account=$billingAccount"
)

Write-Section "啟用必要 APIs"
$apis = @(
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "billingbudgets.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "iap.googleapis.com"
)
Invoke-NativeMutation -Executable $script:Gcloud -Arguments (@("services", "enable") + $apis + @("--project=$projectId"))
Wait-EnabledApis -TargetProjectId $projectId -Services $apis

Write-Section "建立預算警告"
$budgetExists = $false
if ($projectExists) {
    $budgetResult = Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "billing", "budgets", "list", "--billing-account=$billingAccount", "--billing-project=$projectId", "--format=json"
    )
    $budgets = ConvertFrom-JsonOutput -Output $budgetResult.Output
    $budgetExists = @($budgets | Where-Object { $_.displayName -eq "Labor Union Compatibility - $projectId" }).Count -gt 0
}
if ($budgetExists) {
    Write-Host "已存在本Project的compat預算，略過建立。"
}
else {
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "billing", "budgets", "create", "--billing-account=$billingAccount",
        "--billing-project=$projectId",
        "--display-name=Labor Union Compatibility - $projectId", "--budget-amount=$budgetAmount",
        "--filter-projects=projects/$projectId", "--calendar-period=month",
        "--threshold-rule=percent=0.50", "--threshold-rule=percent=0.80", "--threshold-rule=percent=1.00"
    )
}

$assumeAbsent = $DryRun -and (-not $projectExists)
Write-Section "建立VPC與subnet"
if ($assumeAbsent -or (-not (Test-GcloudResource -Arguments @(
    "compute", "networks", "describe", "union-compat-vpc", "--project=$projectId"
)))) {
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "compute", "networks", "create", "union-compat-vpc", "--project=$projectId", "--subnet-mode=custom"
    )
}
if ($assumeAbsent -or (-not (Test-GcloudResource -Arguments @(
    "compute", "networks", "subnets", "describe", "union-compat-run", "--project=$projectId", "--region=$Region"
)))) {
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "compute", "networks", "subnets", "create", "union-compat-run",
        "--project=$projectId", "--region=$Region", "--network=union-compat-vpc",
        "--range=$subnetCidr", "--enable-private-ip-google-access"
    )
}

Write-Section "建立compat Runtime Service Accounts"
$serviceAccounts = @(
    [pscustomobject]@{ Id = "union-api-compat"; Name = "Union API Compatibility Runtime" },
    [pscustomobject]@{ Id = "union-ui-compat"; Name = "Union UI Compatibility Runtime" },
    [pscustomobject]@{ Id = "union-durable-compat"; Name = "Union Durable Worker Compatibility Runtime" },
    [pscustomobject]@{ Id = "union-line-compat"; Name = "Union LINE Worker Compatibility Runtime" },
    [pscustomobject]@{ Id = "union-incident-compat"; Name = "Union Incident Worker Compatibility Runtime" },
    [pscustomobject]@{ Id = "union-monitor-compat"; Name = "Union Monitor Compatibility Runtime" }
)
foreach ($account in $serviceAccounts) {
    Ensure-ServiceAccount -AccountId $account.Id -DisplayName $account.Name -TargetProjectId $projectId -AssumeAbsent:$assumeAbsent
}

$bridgeAddress = Ensure-DevelopmentBridge -TargetProjectId $projectId -TargetRegion $Region -TargetZone $Zone `
    -SubnetCidr $subnetCidr -AssumeAbsent:$assumeAbsent

$operatorMember = if ($activeAccount -match '\.gserviceaccount\.com$') { "serviceAccount:$activeAccount" } else { "user:$activeAccount" }
Ensure-ProjectRole -TargetProjectId $projectId -Member $operatorMember -Role "roles/iap.tunnelResourceAccessor"
Ensure-ProjectRole -TargetProjectId $projectId -Member $operatorMember -Role "roles/compute.osLogin"

Write-Section "建立開發環境 Secrets（內容只經stdin，不進CLI參數、image或Git）"
$secretValues = @(
    [pscustomobject]@{ Name = "union-db-password-compat"; Value = $dbPassword },
    [pscustomobject]@{ Name = "union-totp-keyring-compat"; Value = $totpKeyring },
    [pscustomobject]@{ Name = "union-line-channel-secret-compat"; Value = $lineChannelSecret },
    [pscustomobject]@{ Name = "union-line-access-token-compat"; Value = $lineAccessToken }
)
foreach ($secret in $secretValues) {
    Ensure-Secret -Name $secret.Name -Value $secret.Value -TargetProjectId $projectId -AssumeAbsent:$assumeAbsent
    Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
        "secrets", "add-iam-policy-binding", $secret.Name, "--project=$projectId",
        "--member=serviceAccount:union-api-compat@$projectId.iam.gserviceaccount.com",
        "--role=roles/secretmanager.secretAccessor", "--quiet"
    )
}

Write-Section "啟動本機DB反向SSH Tunnel"
$bridgeManager = Join-Path $PSScriptRoot "manage_gcp_cloud_run_db_bridge.ps1"
& $bridgeManager -Action start -ProjectId $projectId -Zone $Zone -MySqlContainer $mysqlContainer `
    -MySqlContainerPort $mysqlContainerPort -LocalForwardPort 13307 -RemotePort 13306 -DryRun:$DryRun
if (-not $?) { throw "本機DB反向SSH Tunnel啟動失敗。" }

$repository = Select-OrCreateRepository -TargetProjectId $projectId -TargetRegion $Region -AssumeNoRepositories:$assumeAbsent

Write-Section "選擇images、push並部署Cloud Run"
$publisher = Join-Path $PSScriptRoot "publish_gcp_cloud_run_compat.ps1"
if (-not (Test-Path -LiteralPath $publisher -PathType Leaf)) {
    throw "找不到後續發布腳本：$publisher"
}
$publisherParameters = @{
    ProjectId = $projectId
    Region = $Region
    Repository = $repository
    Network = "union-compat-vpc"
    Subnet = "union-compat-run"
    DbHost = $bridgeAddress
    DbPort = 13306
    DbUser = $dbUser
    DbDatabase = $dbDatabase
    LineLiffId = $lineLiffId
    LineLoginChannelId = $lineLoginChannelId
    ApiImage = [string]$builtImages.Api
    UiImage = [string]$builtImages.Ui
    RuntimeOpsImage = [string]$builtImages.RuntimeOps
    InitialProvision = $true
}
if ($DryRun) { $publisherParameters["DryRun"] = $true }
if ($assumeAbsent) { $publisherParameters["AssumeNewProject"] = $true }
& $publisher @publisherParameters
if (-not $?) {
    throw "image發布／Cloud Run部署腳本失敗。"
}

Write-Section "自動驗收"
$apiUrl = if ($DryRun) { "https://union-api-compat-<generated>.$Region.run.app" } else {
    ((Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "run", "services", "describe", "union-api-compat", "--project=$projectId", "--region=$Region", "--format=value(status.url)"
    )).Output -join "").Trim()
}
$uiUrl = if ($DryRun) { "https://union-ui-compat-<generated>.$Region.run.app" } else {
    ((Invoke-NativeRead -Executable $script:Gcloud -Arguments @(
        "run", "services", "describe", "union-ui-compat", "--project=$projectId", "--region=$Region", "--format=value(status.url)"
    )).Output -join "").Trim()
}
Assert-HttpEndpoint -Name "API liveness" -Url "$apiUrl/health"
Assert-HttpEndpoint -Name "Admin UI health" -Url "$uiUrl/_stcore/health"
Assert-HttpEndpoint -Name "LINE webhook GET" -Url "$apiUrl/webhook/line"
Assert-HttpEndpoint -Name "LIFF endpoint" -Url "$apiUrl/liff-page"
Invoke-NativeMutation -Executable $script:Gcloud -Arguments @(
    "run", "jobs", "execute", "union-monitor-compat", "--project=$projectId", "--region=$Region", "--wait", "--quiet"
)
if ($DryRun) {
    Write-Host "DRY_RUN Monitor Job -> Google OIDC -> Private Operations API -> local MySQL bridge"
    Write-Host "AUTOMATED_ACCEPTANCE=NOT_RUN_DRY_RUN"
}
else {
    Write-Host "PASS Monitor Job -> Google OIDC -> Private Operations API -> local MySQL bridge" -ForegroundColor Green
    Write-Host "AUTOMATED_ACCEPTANCE=PASS" -ForegroundColor Green
}

Write-Section "首次設定完成"
Write-Host "Project: $projectId"
Write-Host "Region: $Region"
Write-Host "Artifact Registry: $Region-docker.pkg.dev/$projectId/$repository"
Write-Host "DB bridge VM: $bridgeAddress`:13306 -> IAP reverse SSH -> localhost forward -> $mysqlContainer`:$mysqlContainerPort"
Write-Host "Admin UI: $uiUrl"
Write-Host "LINE Webhook URL: $apiUrl/webhook/line"
Write-Host "LIFF Endpoint URL: $apiUrl/liff-page"
Write-Host "LINE Developers Console: https://developers.line.biz/console/"
Write-Host "Webhook guide: https://developers.line.biz/en/docs/messaging-api/verify-webhook-url/"
Write-Host "LIFF guide: https://developers.line.biz/en/docs/liff/registering-liff-apps/"
Write-Warning "MANUAL_ACCEPTANCE仍需：瀏覽器登入＋TOTP、LINE Console Verify/Use webhook、LIFF app Endpoint URL更新。完成前不得宣稱整體部署驗收完成。"
Write-Warning "開發用 GCE＋IAP反向SSH Tunnel版，嚴禁正式部署。Cloud VPN、地端Router／NAS、Load Balancer／Cloud Armor及正式production gate不在本腳本範圍。"
