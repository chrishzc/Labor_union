#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('menu','start','stop','restart','update','frontend','status','prepare','check','setup','package','database-backup','database-upgrade','database-restore')]
    [string]$Action = 'menu',
    [switch]$LocalOnly
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$runtimeDirectory = Join-Path $ProjectRoot 'scratch\windows-remote'
$statePath = Join-Path $runtimeDirectory 'frontend-control\state.json'
$supervisorPath = Join-Path $PSScriptRoot 'supervise_local_runtime.ps1'
$tokenPath = Join-Path $runtimeDirectory 'cloudflare-state\tunnel-token'
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Assert-NoRemainingRuntime {
    param($State)
    foreach ($root in $State.roots) {
        $child = Get-Process -Id ([int]$root.pid) -ErrorAction SilentlyContinue
        if ($child -and $child.StartTime.ToUniversalTime().Ticks -eq ([datetime]$root.start_time).ToUniversalTime().Ticks) {
            throw 'A registered runtime child is still alive; no process was stopped.'
        }
    }
    # A dead launcher can leave an orphaned Python child. Do not infer that a
    # dead supervisor means its workers stopped. Inspect only native runtime
    # candidates; unknown command lines also prevent recovery. Never kill them.
    $candidates = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='cloudflared.exe'" -ErrorAction Stop)
    foreach ($candidate in $candidates) {
        if ($candidate.Name -eq 'cloudflared.exe') {
            $isService = $candidate.CommandLine -match 'service run'
            if (-not $isService) {
                $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($candidate.ParentProcessId)" -ErrorAction SilentlyContinue
                if ($parent -and $parent.Name -eq 'services.exe') { $isService = $true }
            }
            if ($isService) { continue }
        }
        if (-not $candidate.CommandLine -or $candidate.Name -eq 'cloudflared.exe' -or
            $candidate.CommandLine -match 'uvicorn (api.main:app|scripts.windows_remote_runtime)|-m scripts.run_(line_worker|service_monitor|durable_job_worker|incident_worker|knowledge_worker)') {
            throw 'An unconfirmed runtime or connector may still be running. Close the old installation first; no process was stopped.'
        }
    }
    foreach ($port in @(8000,5173)) {
        $probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
        $probe.Server.ExclusiveAddressUse = $true
        try { $probe.Start() }
        finally { $probe.Stop() }
    }
}

function Get-ManagedState {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
    if ($state.contract -ne 'windows-frontend-control/v1' -or $state.project_root -ne $ProjectRoot -or
        $state.api_port -ne 8000 -or $state.react_port -ne 5173) { throw 'Runtime state belongs to another installation.' }
    $owner = Get-Process -Id ([int]$state.supervisor_pid) -ErrorAction SilentlyContinue
    $alive = $owner -and $owner.StartTime.ToUniversalTime().Ticks -eq ([datetime]$state.supervisor_start_time).ToUniversalTime().Ticks
    if (-not $alive) {
        if ($state.cleanup_confirmed -eq $true) { return $null }
        Assert-NoRemainingRuntime $state
        return $null
    }
    return $state
}

function Assert-ProgramEnvironment {
    if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Run setup first: the project Python environment is missing.' }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'ui_react\node_modules\vite\bin\vite.js'))) {
        throw 'Run setup first: frontend build dependencies are missing.'
    }
}

function Set-RuntimeEnvironment {
    $env:APP_ENV = 'development'
    $env:ACCESS_CONTROL_PROFILE = 'production'
    $env:ENABLE_ADMIN_AUTH = 'true'
    $env:REACT_ADMIN_RUNTIME_PROFILE = 'source'
    $env:REACT_ADMIN_CURRENT_ARTIFACT_DIR = ''
    $env:REACT_ADMIN_PREVIOUS_ARTIFACT_DIR = ''
    $env:REACT_ADMIN_ACTIVE_SELECTOR = ''
    $env:UI_HEALTH_URL = 'http://127.0.0.1:5173/admin/'
    $cfService = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
    $isServiceRunning = ($null -ne $cfService -and $cfService.Status -eq 'Running')
    $env:WINDOWS_REMOTE_TUNNEL_TOKEN_FILE = if ($LocalOnly -or $isServiceRunning) { '' } else { $tokenPath }
}

function New-ManagedArtifact {
    Assert-ProgramEnvironment
    [void][IO.Directory]::CreateDirectory($runtimeDirectory)
    $pointer = Join-Path $runtimeDirectory ('prepared-' + [guid]::NewGuid().ToString('N') + '.txt')
    $previousDotenvSetting = $env:PYTHON_DOTENV_DISABLED
    try {
        $env:PYTHON_DOTENV_DISABLED = '1'
        & $PythonPath -m scripts.windows_remote_runtime --prepare --output-file $pointer | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed; the running version was preserved.' }
    }
    finally { $env:PYTHON_DOTENV_DISABLED = $previousDotenvSetting }
    return [IO.File]::ReadAllText($pointer).Trim()
}

function Stop-ManagedRuntime {
    $state = Get-ManagedState
    if (-not $state) { Write-Host '[Stopped] No managed runtime is running.'; return }
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $supervisorPath `
        -ProjectRoot $ProjectRoot -PythonPath $PythonPath -StopRuntime
    if ($LASTEXITCODE -ne 0) { throw 'Stop failed; do not start another host.' }
}

function Start-ManagedRuntime {
    param([string]$Artifact)
    if (Get-ManagedState) { throw 'This installation is already running. Use update or stop.' }
    Assert-ProgramEnvironment
    Set-RuntimeEnvironment
    $cfService = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
    $isServiceRunning = ($null -ne $cfService -and $cfService.Status -eq 'Running')
    if (-not $LocalOnly -and -not $isServiceRunning) {
        if (-not (Test-Path -LiteralPath $tokenPath -PathType Leaf)) {
            throw '未偵測到運作中的 cloudflared 系統服務，亦無本機 tunnel-token 檔案。請先確認 Windows 服務已啟動，或手動放置 token。'
        }
        $connector = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
        $installedConnector = Join-Path ${env:ProgramFiles(x86)} 'cloudflared\cloudflared.exe'
        if (-not $connector -and -not (Test-Path -LiteralPath $installedConnector)) { throw 'Install cloudflared first.' }
    }
    if (-not $Artifact) { $Artifact = New-ManagedArtifact }
    # Only normal application startup loads its own configuration. The manager
    # never parses or changes .env during startup. Database maintenance is a
    # separate explicit action; startup never performs an upgrade or reset.
    & $PythonPath -m scripts.check_runtime_database
    if ($LASTEXITCODE -ne 0) { throw 'Database readiness failed; no runtime was started.' }
    & docker.exe compose up -d redis
    if ($LASTEXITCODE -ne 0) { throw 'Redis startup failed; no runtime was started.' }
    $env:WINDOWS_REMOTE_ARTIFACT_DIR = $Artifact
    $runLabel = [guid]::NewGuid().ToString('N')
    $logPath = Join-Path $runtimeDirectory ("runtime-$runLabel.log")
    $errorPath = Join-Path $runtimeDirectory ("runtime-$runLabel.stderr.log")
    # Start-Process joins arguments as text on Windows; quote fixed path values.
    $arguments = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$supervisorPath+'"'),
        '-ProjectRoot',('"'+$ProjectRoot+'"'),'-PythonPath',('"'+$PythonPath+'"'))
    $owner = Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError $errorPath -PassThru
    for ($attempt = 0; $attempt -lt 180; $attempt++) {
        if ($owner.HasExited) { throw "Startup failed. See $logPath and $errorPath" }
        if (Test-Path -LiteralPath $statePath) {
            $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
            if ($state.supervisor_pid -eq $owner.Id -and $state.runtime_status -eq 'ready') {
                $remoteUrl = Get-RemoteDisplayUrl
                Write-Host "[Ready] Local: http://localhost:5173/admin/ | Remote: $remoteUrl"
                if ($isServiceRunning) {
                    Write-Host '[Tunnel] Cloudflare Tunnel 透過 Windows 系統服務連線中'
                } elseif (-not $LocalOnly) {
                    Write-Host '[Tunnel started] Check Cloudflare status'
                }
                Write-Host '[Workers] Normal configured background work and push are enabled.'
                return
            }
        }
        Start-Sleep -Seconds 1
    }
    throw "Startup is still pending. Inspect status and $logPath; do not start a second host."
}

function Get-RemoteDisplayUrl {
    $envPath = Join-Path $ProjectRoot '.env'
    if (Test-Path -LiteralPath $envPath) {
        $lines = Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue
        foreach ($line in $lines) {
            if ($line -match '^\s*ALLOWED_ORIGINS\s*=\s*(.+)$') {
                $candidates = $matches[1].Trim() -split ','
                $custom = $candidates | Where-Object { $_ -and $_ -notmatch 'localhost|127\.0\.0\.1' } | Select-Object -First 1
                if ($custom) { return ($custom.Trim().TrimEnd('/') + '/') }
            }
            if ($line -match '^\s*PUBLIC_ORIGIN\s*=\s*(.+)$') {
                $val = $matches[1].Trim()
                if ($val) { return ($val.TrimEnd('/') + '/') }
            }
        }
    }
    return 'https://chrishzc.com/test/'
}

function Show-ManagedStatus {
    $state = Get-ManagedState
    if (-not $state) { Write-Host '[Stopped]'; return }
    $phase = if ($state.runtime_status) { $state.runtime_status } else { 'legacy-ready' }
    Write-Host "Runtime: $phase"
    foreach ($root in $state.roots) {
        $process = Get-Process -Id ([int]$root.pid) -ErrorAction SilentlyContinue
        $alive = $process -and $process.StartTime.ToUniversalTime().Ticks -eq ([datetime]$root.start_time).ToUniversalTime().Ticks
        Write-Host ('{0}: {1}' -f $root.label, $(if ($alive) {'running'} else {'unavailable'}))
    }
    $manifest = Join-Path $state.artifact_path 'artifact-manifest.json'
    if (Test-Path -LiteralPath $manifest) {
        $version = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json
        Write-Host "Frontend: $($version.artifact_version)"
    }
    $remoteUrl = Get-RemoteDisplayUrl
    Write-Host "Local: http://localhost:5173/admin/ | Remote: $remoteUrl"
    Write-Host 'Tunnel process status does not prove external connectivity; check the Cloudflare dashboard.'
}

function Invoke-DatabaseMaintenance {
    param([ValidateSet('backup','upgrade','restore')][string]$Mode)
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw '找不到系統執行環境，請先安裝程式依賴。'
    }
    if ($Mode -ne 'backup' -and (Get-ManagedState)) {
        throw '請先選擇「2 停止全部」，再執行資料庫升級或復原。'
    }
    & $PythonPath -m scripts.nas_database_maintenance $Mode
    if ($LASTEXITCODE -ne 0) {
        throw '資料庫操作未完成；請保留備份與紀錄，依上方訊息處理。'
    }
}

function Invoke-ManagerAction {
    param([string]$Selected)
    if ($Selected -eq 'status') { Show-ManagedStatus; return }
    if ($Selected -eq 'check') {
        Assert-ProgramEnvironment
        if (-not (Get-Command 'docker.exe' -ErrorAction SilentlyContinue)) { throw "docker.exe is missing. 請確認已安裝並啟動 Docker Desktop。" }
        if (-not (Get-Command 'npm.cmd' -ErrorAction SilentlyContinue) -and -not (Get-Command 'npm' -ErrorAction SilentlyContinue)) {
            throw "npm is missing. 請確認已安裝 Node.js (含 npm)。"
        }
        $cf = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
        if ($cf) {
            Write-Host "[PASS] Cloudflare Tunnel 系統服務存在 (狀態: $($cf.Status))"
        }
        Write-Host '[PASS] Program paths present. No configuration, database, provider or Cloudflare access performed.'
        return
    }
    [void][IO.Directory]::CreateDirectory($runtimeDirectory)
    $lock = [IO.File]::Open((Join-Path $runtimeDirectory 'manager.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        switch ($Selected) {
            'database-backup' { Invoke-DatabaseMaintenance 'backup' }
            'database-upgrade' { Invoke-DatabaseMaintenance 'upgrade' }
            'database-restore' { Invoke-DatabaseMaintenance 'restore' }
            'start' { Start-ManagedRuntime }
            'stop' { Stop-ManagedRuntime }
            {$_ -in 'restart','update'} {
                Set-RuntimeEnvironment
                $artifact = New-ManagedArtifact
                Stop-ManagedRuntime
                Start-ManagedRuntime $artifact
            }
            'frontend' {
                Set-RuntimeEnvironment
                $artifact = New-ManagedArtifact
                & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $supervisorPath `
                    -ProjectRoot $ProjectRoot -PythonPath $PythonPath -FrontendArtifact $artifact
                if ($LASTEXITCODE -ne 0) { throw 'Frontend update did not succeed.' }
            }
            'prepare' { [void](New-ManagedArtifact) }
            'setup' {
                if (Get-ManagedState) { throw 'Stop this installation before installing dependencies.' }
                if (-not (Test-Path -LiteralPath $PythonPath)) {
                    $created = $false
                    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
                        foreach ($pyVer in @('-3.14', '-3.13', '-3.12', '-3.11', '-3')) {
                            & py.exe $pyVer -m venv .venv 2>$null
                            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $PythonPath)) {
                                $created = $true
                                break
                            }
                        }
                    }
                    if (-not $created -and (Get-Command python.exe -ErrorAction SilentlyContinue)) {
                        & python.exe -m venv .venv
                        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $PythonPath)) {
                            $created = $true
                        }
                    }
                    if (-not $created) {
                        throw '未找到合適的 Python 執行檔建立 .venv。請確認系統已安裝 Python 3.11+ 並加入 PATH。'
                    }
                }
                Write-Host '正在透過 .venv 安裝 Python 依賴套件 (pip install)...'
                & $PythonPath -m pip install -r requirements.txt
                if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
                Push-Location ui_react
                try {
                    Write-Host '正在安裝前端依賴套件 (npm ci)...'
                    if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
                        & npm.cmd ci
                        if ($LASTEXITCODE -ne 0) {
                            Write-Host 'npm ci 失敗，嘗試 npm install...'
                            & npm.cmd install
                            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
                        }
                    }
                    elseif (Get-Command npm -ErrorAction SilentlyContinue) {
                        & npm ci
                        if ($LASTEXITCODE -ne 0) {
                            Write-Host 'npm ci 失敗，嘗試 npm install...'
                            & npm install
                            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
                        }
                    }
                    else {
                        throw '未找到 npm。請確認該主機已安裝 Node.js (含 npm) 並加入 PATH。'
                    }
                }
                finally { Pop-Location }
                Write-Host '正在安裝 Playwright Chromium...'
                & $PythonPath -m playwright install chromium
                if ($LASTEXITCODE -ne 0) { throw 'Browser dependency installation failed.' }
                Write-Host '[Ready] Program dependencies installed. Prepare this host database, files and configuration separately.'
            }
            'package' {
                if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Run setup first.' }
                & $PythonPath -m scripts.package_windows_runtime
                if ($LASTEXITCODE -ne 0) { throw 'Deployment packaging failed.' }
            }
        }
    }
    finally { $lock.Dispose() }
}

if ($Action -ne 'menu') {
    try { Invoke-ManagerAction $Action; exit 0 }
    catch { Write-Host ('[Error] ' + $_.Exception.Message); exit 1 }
}
while ($true) {
    Write-Host "`nWindows 管理（切換主機前，請先整組停止舊主機）"
    Write-Host '1 啟動全部  2 停止全部  3 套用更新／整組重啟  4 只更新前端'
    Write-Host '5 狀態／版本  6 備份資料庫  7 安全升級資料庫  8 復原資料庫備份'
    Write-Host '9 首次安裝程式依賴  10 檢查程式環境  0 離開'
    $choice = Read-Host '請選擇'
    if ($choice -eq '0') { break }
    $actions = @{'1'='start';'2'='stop';'3'='update';'4'='frontend';'5'='status';'6'='database-backup';'7'='database-upgrade';'8'='database-restore';'9'='setup';'10'='check'}
    if (-not $actions.ContainsKey($choice)) { continue }
    try { Invoke-ManagerAction $actions[$choice] }
    catch { Write-Host ('[Error] ' + $_.Exception.Message) }
}
