#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet("start", "stop", "status")][string]$Action,
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Zone = "asia-east1-b",
    [string]$Instance = "union-db-bridge-compat",
    [string]$MySqlContainer = "mysql_db",
    [ValidateRange(1, 65535)][int]$MySqlContainerPort = 3306,
    [ValidateRange(1024, 65535)][int]$LocalForwardPort = 13307,
    [ValidateRange(1024, 65535)][int]$RemotePort = 13306,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# DEVELOPMENT ONLY: this launcher creates no production-grade connectivity and must
# never be used as a replacement for the approved Cloud VPN -> NAS deployment.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$stateDirectory = Join-Path $projectRoot "scratch\cloud-run-db-bridge\$ProjectId"
$pidPath = Join-Path $stateDirectory "gce-iap-reverse-ssh.pid"
$stdoutPath = Join-Path $stateDirectory "gce-iap-reverse-ssh.stdout.log"
$stderrPath = Join-Path $stateDirectory "gce-iap-reverse-ssh.stderr.log"
$sshConfigPath = Join-Path $stateDirectory "gce-iap-reverse-ssh.config"
$knownHostsPath = Join-Path $stateDirectory "known_hosts"
$identityPath = Join-Path $stateDirectory "union-compat-ed25519"
$publicKeyPath = "$identityPath.pub"
$legacyPidPath = Join-Path $projectRoot "scratch\cloud-run-db-bridge\gce-iap-reverse-ssh.pid"
$forwardContainer = "union-local-mysql-forward-compat"

function Resolve-GcloudCommand {
    $command = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        $command = Get-Command "gcloud" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($null -eq $command) { throw "找不到 gcloud CLI。" }
    return $command.Source
}

function Resolve-OpenSshCommand {
    $command = Get-Command "ssh.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "找不到 Windows OpenSSH ssh.exe。" }
    return $command.Source
}

function Resolve-RequiredCommand {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "找不到必要工具'$Name'。" }
    return $command.Source
}

function Invoke-GcloudReadWithRetry {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [switch]$AllowFailure)
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $script:Gcloud
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
        if (($exitCode -eq 0) -or (-not $retryable) -or ($attempt -eq 6)) { break }
        $delay = [Math]::Min(30, [Math]::Pow(2, $attempt)) + (Get-Random -Minimum 0 -Maximum 3)
        Write-Warning "GCP暫時性錯誤；$delay 秒後重試（$attempt/6）。"
        Start-Sleep -Seconds $delay
    }
    if (($exitCode -ne 0) -and (-not $AllowFailure)) { throw "gcloud命令失敗：gcloud $($Arguments -join ' ')`n$detail" }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
}

function Set-RestrictedSshAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Grant
    )
    $currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $currentAccount = $currentIdentity.Name
    $allowedSids = @($currentIdentity.User.Value, "S-1-5-18")
    $null = & $script:Icacls $Path "/inheritance:r" "/grant:r" "${currentAccount}:$Grant" "SYSTEM:$Grant"
    if ($LASTEXITCODE -ne 0) { throw "無法收緊SSH ACL：$Path" }

    # ssh-keygen may add an explicit BUILTIN\Administrators ACE even after the
    # parent directory is restricted. Remove known broad principals, then verify
    # the resulting ACL instead of trusting a successful icacls exit code.
    foreach ($sid in @("*S-1-5-32-544", "*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0")) {
        $null = & $script:Icacls $Path "/remove:g" $sid
        if ($LASTEXITCODE -ne 0) { throw "無法移除SSH ACL broad principal '$sid'：$Path" }
        $null = & $script:Icacls $Path "/remove:d" $sid
        if ($LASTEXITCODE -ne 0) { throw "無法移除SSH ACL deny principal '$sid'：$Path" }
    }

    $acl = Get-Acl -LiteralPath $Path
    if (-not $acl.AreAccessRulesProtected) { throw "SSH ACL仍允許繼承：$Path" }
    $actualSids = @($acl.Access | ForEach-Object {
        $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    } | Sort-Object -Unique)
    $unexpected = @($actualSids | Where-Object { $_ -notin $allowedSids })
    $missing = @($allowedSids | Where-Object { $_ -notin $actualSids })
    if (($unexpected.Count -gt 0) -or ($missing.Count -gt 0)) {
        throw "SSH ACL驗證失敗；只允許目前Windows使用者與SYSTEM：$Path"
    }
}

function Ensure-DedicatedSshIdentity {
    if ($DryRun) {
        Write-Host "[DRY-RUN] 產生Project專用Ed25519 key、收緊ACL並登錄OS Login：$identityPath"
        return
    }
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    if (-not (Test-Path -LiteralPath $identityPath -PathType Leaf)) {
        $arguments = @("-t", "ed25519", "-N", "", "-f", $identityPath, "-C", "labor-union-compat-$ProjectId")
        $output = @(& $script:SshKeygen @arguments 2>&1)
        if ($LASTEXITCODE -ne 0) { throw "產生Project專用SSH key失敗：$($output -join "`n")" }
    }
    if (-not (Test-Path -LiteralPath $publicKeyPath -PathType Leaf)) { throw "SSH public key缺失：$publicKeyPath" }

    Set-RestrictedSshAcl -Path $stateDirectory -Grant "(OI)(CI)F"
    foreach ($path in @($identityPath, $publicKeyPath)) {
        Set-RestrictedSshAcl -Path $path -Grant "F"
    }
    $null = Invoke-GcloudReadWithRetry -Arguments @(
        "compute", "os-login", "ssh-keys", "add", "--key-file=$publicKeyPath", "--ttl=30d", "--project=$ProjectId", "--quiet"
    )
    $profileResult = Invoke-GcloudReadWithRetry -Arguments @(
        "compute", "os-login", "describe-profile", "--project=$ProjectId", "--format=json"
    )
    $profile = (($profileResult.Output -join "`n") | ConvertFrom-Json)
    $expectedPublicKey = (Get-Content -LiteralPath $publicKeyPath -Raw -Encoding utf8).Trim()
    $registered = @($profile.sshPublicKeys.PSObject.Properties | Where-Object {
        ([string]$_.Value.key).Trim() -eq $expectedPublicKey
    })
    if ($registered.Count -ne 1) { throw "OS Login讀回驗證未找到唯一Project專用SSH public key。" }
    Write-Host "[PASS] Project專用SSH key已產生、ACL已收緊並登錄OS Login。" -ForegroundColor Green
}

function Assert-DevelopmentProject {
    if ($DryRun) { return }
    $result = Invoke-GcloudReadWithRetry -Arguments @("projects", "describe", $ProjectId, "--format=json")
    $project = ($result.Output -join "`n") | ConvertFrom-Json
    $environment = [string]$project.labels.environment
    $deployment = [string]$project.labels.deployment
    if (($environment -notin @("staging", "test")) -or ($deployment -ne "compat")) {
        throw "此工具只允許 environment=staging/test 且 deployment=compat 的開發 Project。"
    }
}

function Get-RecordedProcess {
    param([string]$Path = $pidPath)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $raw = (Get-Content -LiteralPath $Path -Raw -Encoding utf8).Trim()
    $processId = 0
    if (-not [int]::TryParse($raw, [ref]$processId)) { return $null }
    return Get-Process -Id $processId -ErrorAction SilentlyContinue
}

function Remove-StaleRemoteListener {
    if (-not (Test-Path -LiteralPath $sshConfigPath -PathType Leaf)) { return }
    if ($DryRun) {
        Write-Host "[DRY-RUN] 清理GCE compat專用TCP/$RemotePort殘留listener。"
        return
    }
    $remoteCommand = "if ss -ltn 'sport = :$RemotePort' | grep -q ':$RemotePort '; then sudo fuser -k $RemotePort/tcp >/dev/null 2>&1; fi"
    $output = @(& $script:Ssh -F $sshConfigPath "union-db-bridge-compat-iap" $remoteCommand 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "無法清理GCE compat專用TCP/$RemotePort殘留listener：$($output -join "`n")"
    }
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        $null = & $script:Ssh -F $sshConfigPath "union-db-bridge-compat-iap" `
            "! ss -ltn 'sport = :$RemotePort' | grep -q ':$RemotePort '" 2>$null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "GCE compat專用TCP/$RemotePort殘留listener未在期限內釋放。"
}

$script:Gcloud = Resolve-GcloudCommand
$script:Ssh = Resolve-OpenSshCommand
$script:SshKeygen = Resolve-RequiredCommand -Name "ssh-keygen.exe"
$script:Icacls = Resolve-RequiredCommand -Name "icacls.exe"
Assert-DevelopmentProject

if ($Action -eq "status") {
    $process = Get-RecordedProcess
    if ($null -eq $process) {
        Write-Host "DB bridge：STOPPED"
        exit 1
    }
    Write-Host "DB bridge：RUNNING（PID=$($process.Id)）"
    exit 0
}

if ($Action -eq "stop") {
    $processes = [System.Collections.Generic.List[object]]::new()
    foreach ($recordedPath in @($pidPath, $legacyPidPath)) {
        $recorded = Get-RecordedProcess -Path $recordedPath
        if ($null -ne $recorded) {
            if ($recorded.ProcessName -notmatch '^ssh$') {
                throw "PID檔'$recordedPath'指向非ssh程序'$($recorded.ProcessName)'，為避免誤殺已停止。"
            }
            if (@($processes | Where-Object { $_.Id -eq $recorded.Id }).Count -eq 0) { $processes.Add($recorded) }
        }
    }
    Remove-StaleRemoteListener
    if ($processes.Count -eq 0) {
        Write-Host "DB bridge 已停止。"
    }
    else {
        foreach ($process in $processes) {
            if ($DryRun) { Write-Host "[DRY-RUN] taskkill /PID $($process.Id) /T /F" }
            else { & taskkill.exe /PID $process.Id /T /F *> $null }
        }
    }
    if (-not $DryRun) {
        foreach ($recordedPath in @($pidPath, $legacyPidPath)) {
            if (Test-Path -LiteralPath $recordedPath) { Remove-Item -LiteralPath $recordedPath -Force }
        }
    }
    if ($DryRun) { Write-Host "[DRY-RUN] docker stop $forwardContainer" }
    else {
        & docker stop $forwardContainer *> $null
        if (($LASTEXITCODE -ne 0) -and ($LASTEXITCODE -ne 1)) { throw "停止本機 MySQL forward container失敗。" }
    }
    exit 0
}

$currentProcess = Get-RecordedProcess
if ($null -ne $currentProcess) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] DB bridge已在執行（PID=$($currentProcess.Id)）；不重啟、不修改。"
        exit 0
    }
    throw "DB bridge 已在執行；請先使用 -Action status 或 stop。"
}
$legacyProcess = Get-RecordedProcess -Path $legacyPidPath
if ($null -ne $legacyProcess) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] 偵測到舊版DB bridge PID=$($legacyProcess.Id)；實際執行前須先-Action stop。"
        exit 0
    }
    throw "偵測到舊版DB bridge PID；請先執行本腳本的-Action stop完成安全收斂。"
}
if (-not $DryRun) {
    & docker inspect --format "{{.State.Running}}" $MySqlContainer *> $null
    if ($LASTEXITCODE -ne 0) { throw "找不到執行中的 MySQL container '$MySqlContainer'。" }
    & $script:Gcloud compute instances describe $Instance --project=$ProjectId --zone=$Zone --format="value(name)" *> $null
    if ($LASTEXITCODE -ne 0) { throw "找不到開發用中繼 VM '$Instance'。請先執行首次部署腳本。" }
}

$network = if ($DryRun) { "<mysql-container-network>" } else {
    $networkResult = & docker inspect $MySqlContainer --format "{{range `$name,`$value := .NetworkSettings.Networks}}{{println `$name}}{{end}}"
    if ($LASTEXITCODE -ne 0) { throw "無法讀取 MySQL container network。" }
    [string]($networkResult | Select-Object -First 1)
}
if ([string]::IsNullOrWhiteSpace($network)) { throw "MySQL container沒有可用的Docker network。" }
$forwardScript = Join-Path $PSScriptRoot "local_mysql_tcp_forward.py"
$mount = "$forwardScript`:/opt/local_mysql_tcp_forward.py:ro"
$forwardArguments = @(
    "run", "-d", "--rm", "--name", $forwardContainer, "--network", $network,
    "-p", "127.0.0.1:${LocalForwardPort}:13306", "-v", $mount,
    "python:3.12.13-slim-trixie", "python", "/opt/local_mysql_tcp_forward.py",
    "--listen-port", "13306", "--upstream-host", $MySqlContainer, "--upstream-port", [string]$MySqlContainerPort
)
if ($DryRun) { Write-Host "[DRY-RUN] docker $($forwardArguments -join ' ')" }
else {
    & docker rm -f $forwardContainer *> $null
    & docker @forwardArguments *> $null
    if ($LASTEXITCODE -ne 0) { throw "啟動只綁localhost的MySQL forward container失敗。" }
    Start-Sleep -Seconds 2
    if (-not (Test-NetConnection -ComputerName "127.0.0.1" -Port $LocalForwardPort -InformationLevel Quiet)) {
        throw "本機 MySQL forward 127.0.0.1:$LocalForwardPort 未就緒。"
    }
}

Ensure-DedicatedSshIdentity
$osLoginUser = if ($DryRun) { "<os-login-user>" } else {
    [string](((Invoke-GcloudReadWithRetry -Arguments @("compute", "os-login", "describe-profile", "--project=$ProjectId", "--format=value(posixAccounts[0].username)" )).Output -join "").Trim())
}
$instanceId = if ($DryRun) { "<instance-id>" } else {
    [string](((Invoke-GcloudReadWithRetry -Arguments @("compute", "instances", "describe", $Instance, "--project=$ProjectId", "--zone=$Zone", "--format=value(id)" )).Output -join "").Trim())
}
if ((-not $DryRun) -and (([string]::IsNullOrWhiteSpace($osLoginUser)) -or ([string]::IsNullOrWhiteSpace($instanceId)) -or (-not (Test-Path -LiteralPath $identityPath)))) {
    throw "缺少OS Login user、instance ID或Project專用OpenSSH key，不能啟動Tunnel。"
}
$gcloudConfigPath = $script:Gcloud.Replace("\", "/")
$identityConfigPath = $identityPath.Replace("\", "/")
$knownHostsConfigPath = $knownHostsPath.Replace("\", "/")
$sshConfig = @"
Host union-db-bridge-compat-iap
    HostName compute.$instanceId
    User $osLoginUser
    IdentityFile "$identityConfigPath"
    IdentitiesOnly yes
    ProxyCommand "$gcloudConfigPath" compute start-iap-tunnel $Instance %p --listen-on-stdin --project=$ProjectId --zone=$Zone --verbosity=warning
    StrictHostKeyChecking accept-new
    UserKnownHostsFile "$knownHostsConfigPath"
    RequestTTY no
    ExitOnForwardFailure yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
"@
$sshArguments = @(
    "-F", $sshConfigPath, "union-db-bridge-compat-iap", "-N",
    "-R", "0.0.0.0:${RemotePort}:127.0.0.1:$LocalForwardPort"
)
if ($DryRun) {
    Write-Host "[DRY-RUN] write OpenSSH config under $stateDirectory"
    Write-Host "[DRY-RUN] $script:Ssh $($sshArguments -join ' ')"
    exit 0
}

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
[System.IO.File]::WriteAllText($sshConfigPath, $sshConfig, [System.Text.UTF8Encoding]::new($false))
Remove-StaleRemoteListener
$process = Start-Process -FilePath $script:Ssh -ArgumentList $sshArguments -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
$process.Id | Set-Content -LiteralPath $pidPath -Encoding utf8NoBOM
Start-Sleep -Seconds 5
$process.Refresh()
if ($process.HasExited) {
    $errorText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw -Encoding utf8 } else { "" }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    & docker stop $forwardContainer *> $null
    throw "反向 SSH Tunnel 啟動失敗：$errorText"
}
$null = & $script:Ssh -F $sshConfigPath union-db-bridge-compat-iap "ss -ltn | grep -q ':$RemotePort '" 2>$null
if ($LASTEXITCODE -ne 0) {
    & taskkill.exe /PID $process.Id /T /F *> $null
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    & docker stop $forwardContainer *> $null
    throw "GCE reverse port $RemotePort 未監聽，Tunnel驗收失敗。"
}

Write-Host "DB bridge：RUNNING（PID=$($process.Id)）" -ForegroundColor Green
Write-Warning "僅供開發測試；電腦休眠、斷網或停止此程序後，Cloud Run DB readiness 會失敗。"
