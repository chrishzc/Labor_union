"""Windows handoff excludes local secrets; manager actions retain owned lifecycle."""
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

from scripts.package_windows_runtime import included, package

ROOT = Path(__file__).resolve().parents[7]
MANAGER = ROOT / 'scripts/launchers/manage_windows.ps1'
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


def run_manager_functions(script, directory, **environment):
    load = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Manager syntax error'}
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$ProjectRoot=$env:MANAGER_TEST_DIRECTORY
$runtimeDirectory=Join-Path $ProjectRoot 'scratch\windows-remote'
$statePath=Join-Path $runtimeDirectory 'frontend-control\state.json'
'''
    return subprocess.run(
        [str(POWERSHELL), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', load + script],
        env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER),
             'MANAGER_TEST_DIRECTORY': str(directory), **environment},
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows UTF-8 control channel')
@pytest.mark.parametrize('action', ['stop', 'frontend', 'status'])
def test_bomless_state_preserves_chinese_and_quoted_paths(tmp_path, action):
    root = tmp_path / "獅子 [管理] & O'Brien" / 'Labor union'
    root.mkdir(parents=True)
    supervisor = root / 'supervisor.ps1'
    supervisor.write_text(r'''
param($ProjectRoot,$PythonPath,[switch]$StopRuntime,$FrontendArtifact)
$ErrorActionPreference='Stop'
[void][IO.Directory]::CreateDirectory((Join-Path $ProjectRoot 'control-reached'))
[IO.File]::WriteAllText((Join-Path $ProjectRoot 'received-root.txt'),$ProjectRoot)
''', encoding='utf-8')
    result = run_manager_functions(r'''
. $env:CONTROL_TEST_PATH
# Emulate a non-UTF-8 Windows default, even on machines with UTF-8 ACP enabled.
$PSDefaultParameterValues['Get-Content:Encoding']='Ascii'
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $statePath))
Write-FrontendControlJson $statePath @{
    contract='windows-frontend-control/v1';project_root=$ProjectRoot
    supervisor_pid=$PID;supervisor_start_time=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
    api_port=8000;react_port=5173;runtime_status='ready';roots=@()
}
$state=Get-ManagedState
if($state.project_root -cne $ProjectRoot){throw 'UTF-8 project root was corrupted'}
$supervisorPath=Join-Path $ProjectRoot 'supervisor.ps1'
$PythonPath='unused-python'
function Set-RuntimeEnvironment {}
function New-ManagedArtifact {return (Join-Path $ProjectRoot 'artifact')}
function Get-RemoteDisplayUrl {return 'https://example.invalid/'}
Invoke-ManagerAction $env:ACTION_TEST
''', root, ACTION_TEST=action,
        CONTROL_TEST_PATH=str(ROOT / 'scripts/launchers/windows_frontend_control.ps1'))
    assert result.returncode == 0, result.stdout + result.stderr
    if action != 'status':
        assert (root / 'received-root.txt').read_text(encoding='utf-8-sig') == str(root)


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows UTF-8 request channel')
def test_supervisor_reads_utf8_state_and_frontend_request_with_legacy_default(tmp_path):
    root = tmp_path / '獅子 管理'
    root.mkdir()
    result = run_manager_functions(r'''
. $env:CONTROL_TEST_PATH
$PSDefaultParameterValues['Get-Content:Encoding']='Ascii'
$ApiPort=8000;$ReactPort=5173;$script:RunId='utf8-test'
$script:Owned=@();$script:CleanupSucceeded=$false
function Get-ProcessSnapshot {
    param($ProcessId)
    return [pscustomobject]@{State='alive';StartTime=(Get-Process -Id $PID).StartTime.ToUniversalTime()}
}
function Test-SameProcessIdentity {
    param($Entry,$Snapshot)
    return $Entry.StartTime.ToUniversalTime().Ticks -eq $Snapshot.StartTime.ToUniversalTime().Ticks
}
function Write-RuntimeEvent {}
Publish-FrontendControlState
$state=Get-FrontendUpdateSupervisor
if($state.project_root -cne $ProjectRoot){throw 'Supervisor read corrupted installation root'}
$artifact=Join-Path $ProjectRoot 'scratch\windows-remote\artifact-candidate'
function Invoke-RemoteFrontendRestart {
    param($ArtifactPath)
    if($ArtifactPath -cne $artifact){throw 'Supervisor read corrupted artifact path'}
    return @{status='updated'}
}
$id='a'*32
Write-FrontendControlJson (Join-Path (Get-FrontendControlDirectory) 'request.json') @{
    id=$id;run_id=$script:RunId;operation='restart_frontend';artifact_path=$artifact
}
Receive-FrontendControlRequest
$response=[IO.File]::ReadAllText((Join-Path (Get-FrontendControlDirectory) ($id+'.response.json')))|ConvertFrom-Json
if($response.status -ne 'updated'){throw ('Request rejected: '+$response.error)}
''', root, CONTROL_TEST_PATH=str(ROOT / 'scripts/launchers/windows_frontend_control.ps1'))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows installation binding')
def test_live_foreign_state_is_rejected_even_inside_current_state_directory(tmp_path):
    result = run_manager_functions(r'''
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $statePath))
[IO.File]::WriteAllText($statePath,(@{
    contract='windows-frontend-control/v1';project_root='C:\another-installation'
    supervisor_pid=$PID;supervisor_start_time=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
    api_port=8000;react_port=5173
}|ConvertTo-Json))
$rejected=$false
try{Get-ManagedState|Out-Null}catch{$rejected=$true}
if(-not $rejected){throw 'Foreign live installation was accepted'}
''', tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows batch menu')
def test_batch_menu_dispatches_every_option_and_continues_after_error(tmp_path):
    root = tmp_path / '獅子 管理'
    launcher = root / 'scripts/launchers/manage_windows.ps1'
    launcher.parent.mkdir(parents=True)
    record = r'''
function Invoke-ManagerAction {
    param($Selected)
    [IO.File]::AppendAllText((Join-Path $ProjectRoot 'actions.txt'),$Selected+"`n")
    if($Selected -eq 'stop'){throw 'synthetic stop failure'}
}
'''
    launcher.write_text(MANAGER.read_text(encoding='utf-8-sig').replace(
        "if ($Action -ne 'menu') {", record + "\nif ($Action -ne 'menu') {"), encoding='utf-8-sig')
    entry = root / 'Windows管理.bat'
    entry.write_bytes((ROOT / entry.name).read_bytes())
    result = subprocess.run(['cmd.exe', '/d', '/c', 'call', str(entry)],
                            input='invalid\n' + '\n'.join(map(str, range(1, 11))) + '\n0\n',
                            capture_output=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / 'actions.txt').read_text(encoding='utf-8').splitlines() == [
        'start', 'stop', 'update', 'frontend', 'status', 'database-backup',
        'database-upgrade', 'database-restore', 'setup', 'check',
    ]
    assert '[Error] synthetic stop failure' in result.stdout
    failed = subprocess.run(['cmd.exe', '/d', '/c', 'call', str(entry), '-Action', 'stop'],
                            input='\n', capture_output=True, encoding='utf-8', errors='replace', timeout=30)
    assert failed.returncode == 1, failed.stdout + failed.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows startup ordering')
@pytest.mark.parametrize('failure', ['', 'build', 'database', 'redis', 'supervisor'])
def test_start_checks_build_database_and_redis_before_launching(tmp_path, failure):
    result = run_manager_functions(r'''
$LocalOnly=$true
$PythonPath='Invoke-TestPython'
$supervisorPath='unused-supervisor'
$script:calls=[System.Collections.Generic.List[string]]::new()
function Get-ManagedState {return $null}
function Assert-ProgramEnvironment {}
function Set-RuntimeEnvironment {}
function Get-Service {param($Name,$ErrorAction);return $null}
function Get-RemoteDisplayUrl {return 'https://example.invalid/'}
function New-ManagedArtifact {
    $script:calls.Add('build')
    if($env:FAIL_AT -eq 'build'){throw 'build failed'}
    return (Join-Path $ProjectRoot 'artifact')
}
function Invoke-TestPython {
    if(($args -join '|') -ne '-m|scripts.check_runtime_database'){throw 'Unexpected Python invocation'}
    $script:calls.Add('database');$global:LASTEXITCODE=[int]($env:FAIL_AT -eq 'database')
}
function docker.exe {
    if(($args -join '|') -ne 'compose|up|-d|redis'){throw 'Unexpected container operation'}
    $script:calls.Add('redis');$global:LASTEXITCODE=[int]($env:FAIL_AT -eq 'redis')
}
function Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,$RedirectStandardOutput,$RedirectStandardError,[switch]$PassThru)
    if($WindowStyle -ne 'Hidden' -or $WorkingDirectory -ne $ProjectRoot){throw 'Wrong supervisor launch'}
    $script:calls.Add('supervisor')
    return [pscustomobject]@{Id=777;HasExited=($env:FAIL_AT -eq 'supervisor')}
}
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $statePath))
[IO.File]::WriteAllText($statePath,'{"supervisor_pid":777,"runtime_status":"ready"}')
$rejected=$false
try{Invoke-ManagerAction start}catch{$rejected=$true}
if($rejected -ne [bool]$env:FAIL_AT){throw 'Startup failure was hidden or startup failed'}
$expected=@('build','database','redis','supervisor')
if($env:FAIL_AT){$expected=$expected[0..([array]::IndexOf($expected,$env:FAIL_AT))]}
if(($script:calls -join ',') -ne ($expected -join ',')){throw ('Unexpected startup effects: '+($script:calls -join ','))}
''', tmp_path, FAIL_AT=failure)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows setup failure propagation')
@pytest.mark.parametrize('failure', ['', 'pip', 'npm', 'browser'])
def test_setup_checks_each_dependency_step_and_stops_on_failure(tmp_path, failure):
    (tmp_path / 'ui_react').mkdir()
    result = run_manager_functions(r'''
Set-Location -LiteralPath $ProjectRoot
$PythonPath='Invoke-TestPython'
$script:calls=[System.Collections.Generic.List[string]]::new()
function Get-ManagedState {return $null}
function Test-Path {param($LiteralPath);return $true}
function Get-Command {param($Name,$ErrorAction);return [pscustomobject]@{Name=$Name}}
function Invoke-TestPython {
    $step=if($args[1] -eq 'pip'){'pip'}elseif(($args -join '|') -eq '-m|playwright|install|chromium'){'browser'}else{throw 'Unexpected dependency command'}
    $script:calls.Add($step);$global:LASTEXITCODE=[int]($env:FAIL_AT -eq $step)
}
function npm.cmd {
    $script:calls.Add('npm:'+$args[0]);$global:LASTEXITCODE=[int]($env:FAIL_AT -eq 'npm')
}
$rejected=$false
try{Invoke-ManagerAction setup}catch{$rejected=$true}
if($rejected -ne [bool]$env:FAIL_AT){throw 'Dependency failure was hidden or setup failed'}
$expected=switch($env:FAIL_AT){
    'pip' {'pip'}
    'npm' {'pip,npm:ci,npm:install'}
    default {'pip,npm:ci,browser'}
}
if(($script:calls -join ',') -ne $expected){throw ('Unexpected dependency effects: '+($script:calls -join ','))}
if((Get-Location).Path -ne $ProjectRoot){throw 'Setup failed to restore the working directory'}
''', tmp_path, FAIL_AT=failure)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows stop failure propagation')
def test_update_never_restarts_when_supervisor_rejects_stop(tmp_path):
    result = run_manager_functions(r'''
$script:starts=0
function Set-RuntimeEnvironment {}
function New-ManagedArtifact {return 'validated-artifact'}
function Get-ManagedState {return [pscustomobject]@{project_root=$ProjectRoot}}
function powershell.exe {$global:LASTEXITCODE=7}
function Start-ManagedRuntime {$script:starts++}
$rejected=$false
try{Invoke-ManagerAction update}catch{$rejected=$true}
if(-not $rejected -or $script:starts -ne 0){throw 'Restarted after failed stop'}
''', tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows environment check')
@pytest.mark.parametrize('missing', ['', 'python', 'vite', 'docker', 'npm'])
def test_environment_check_reports_missing_requirements_without_external_calls(tmp_path, missing):
    result = run_manager_functions(r'''
$PythonPath=Join-Path $ProjectRoot '.venv\Scripts\python.exe'
function Test-Path {
    param($LiteralPath)
    return -not (($env:MISSING_TEST -eq 'python' -and $LiteralPath -eq $PythonPath) -or
        ($env:MISSING_TEST -eq 'vite' -and $LiteralPath -like '*vite.js'))
}
function Get-Command {
    param($Name,$ErrorAction)
    if(($env:MISSING_TEST -eq 'docker' -and $Name -eq 'docker.exe') -or
        ($env:MISSING_TEST -eq 'npm' -and $Name -like 'npm*')){return $null}
    return [pscustomobject]@{Name=$Name}
}
function Get-Service {param($Name,$ErrorAction);return $null}
function Invoke-DatabaseMaintenance {throw 'Environment check reached database'}
function docker.exe {throw 'Environment check ran Docker'}
function npm.cmd {throw 'Environment check installed dependencies'}
$rejected=$false
try{Invoke-ManagerAction check}catch{$rejected=$true}
if($rejected -ne [bool]$env:MISSING_TEST){throw 'Wrong environment check result'}
''', tmp_path, MISSING_TEST=missing)
    assert result.returncode == 0, result.stdout + result.stderr


def test_deployment_archive_never_opens_excluded_settings_or_runtime_data(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    program = {'Windows管理.bat', 'scripts/launchers/manage_windows.ps1',
               'scripts/windows_remote_runtime.py', 'requirements.txt', 'ui_react/package-lock.json'}
    secrets = {'.env', 'ui_react/.env.production', 'config/credentials.json',
               'scratch/windows-remote/cloudflare-state/tunnel-token', 'backups/database.sql',
               'runtime_data/photo.jpg', 'logs/events.log', 'config/private.key'}
    for name in program | secrets:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic fixture', encoding='utf-8')
    original_read = Path.read_bytes

    def guarded_read(path):
        assert path.relative_to(tmp_path).as_posix() not in secrets, 'Secret file was opened'
        return original_read(path)

    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    output = tmp_path / 'handoff.zip'
    manifest = package(output, root=tmp_path)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == program | {'windows-release.json'}
        assert json.loads(archive.read('windows-release.json')) == manifest
    with pytest.raises(ValueError, match='already exists'):
        package(output, root=tmp_path)


@pytest.mark.parametrize('name', ['.env', 'config/.env.local', 'config/service_account.json',
                                  'config/private.pfx', 'line/token.json', 'ui_react/node_modules/a.js'])
def test_secret_names_are_rejected_before_open(name):
    assert not included(name)


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows database menu')
def test_database_menu_dispatches_three_existing_operations_without_packaging(tmp_path):
    script = r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Manager syntax error'}
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$runtimeDirectory=$env:MANAGER_TEST_DIRECTORY
$script:databaseCalls=[System.Collections.Generic.List[string]]::new()
$script:shown=[System.Collections.Generic.List[string]]::new()
$script:choices=[System.Collections.Generic.Queue[string]]::new()
foreach($value in @('6','7','8','0')){$script:choices.Enqueue($value)}
function Read-Host {param($Prompt);return $script:choices.Dequeue()}
function Write-Host {$script:shown.Add(($args -join ' '))}
function Invoke-DatabaseMaintenance {param($Mode);$script:databaseCalls.Add($Mode)}
function Stop-ManagedRuntime {throw 'Menu must not stop services implicitly'}
function Start-ManagedRuntime {throw 'Menu must not start services implicitly'}
$menu=@($ast.EndBlock.Statements | Where-Object {$_ -is [System.Management.Automation.Language.WhileStatementAst]})
if($menu.Count -ne 1){throw 'Expected one manager menu'}
Invoke-Expression $menu[0].Extent.Text
if(($script:databaseCalls -join ',') -ne 'backup,upgrade,restore'){throw 'Wrong database operation dispatch'}
if(($script:shown -join ',') -match '產生部署包'){throw 'Packaging is still in the daily menu'}
if(($script:shown -join ',') -notmatch '10 檢查程式環境'){throw 'Renumbered environment check is missing'}
Write-Output 'PASS'
'''
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', script],
                            env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER),
                                 'MANAGER_TEST_DIRECTORY': str(tmp_path)},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout

@pytest.mark.skipif(os.name != 'nt', reason='Native Windows database admission')
def test_database_delegate_requires_stop_for_upgrade_restore_and_propagates_failure():
    script = r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Manager syntax error'}
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$PythonPath='Invoke-TestPython'
$script:running=$true;$script:pythonExit=0;$script:stops=0
$script:calls=[System.Collections.Generic.List[string]]::new()
function Test-Path {param($LiteralPath,$PathType);return $true}
function Get-ManagedState {if($script:running){return [pscustomobject]@{runtime_status='ready'}};return $null}
function Invoke-TestPython {$script:calls.Add(($args -join '|'));$global:LASTEXITCODE=$script:pythonExit}
function Stop-ManagedRuntime {$script:stops++;throw 'Implicit stop forbidden'}
function Assert-ProgramEnvironment {throw 'Database tools must not require frontend dependencies'}
Invoke-DatabaseMaintenance backup
foreach($mode in @('upgrade','restore')){
    $rejected=$false
    try{Invoke-DatabaseMaintenance $mode}catch{$rejected=$true}
    if(-not $rejected -or $script:calls.Count -ne 1 -or $script:stops -ne 0){throw 'Live runtime admitted for database switch'}
}
$script:running=$false
Invoke-DatabaseMaintenance upgrade
Invoke-DatabaseMaintenance restore
if(($script:calls -join ',') -ne '-m|scripts.nas_database_maintenance|backup,-m|scripts.nas_database_maintenance|upgrade,-m|scripts.nas_database_maintenance|restore'){throw 'Wrong maintenance transport'}
$script:pythonExit=7;$rejected=$false
try{Invoke-DatabaseMaintenance backup}catch{$rejected=$true}
if(-not $rejected -or $script:stops -ne 0){throw 'Database failure was hidden or services stopped'}
Write-Output 'PASS'
'''
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', script],
                            env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER)},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout

@pytest.mark.skipif(os.name != 'nt', reason='Native Windows manager')
def test_update_builds_before_stop_and_preserves_full_group_on_build_failure(tmp_path):
    script = r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Manager syntax error'}
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$runtimeDirectory=$env:MANAGER_TEST_DIRECTORY
$script:actions=[System.Collections.Generic.List[string]]::new()
function Set-RuntimeEnvironment {}
function New-ManagedArtifact { $script:actions.Add('build'); throw 'synthetic build failure' }
function Stop-ManagedRuntime { $script:actions.Add('stop') }
function Start-ManagedRuntime {param($Artifact);$script:actions.Add('start:'+ $Artifact)}
$rejected=$false
try{Invoke-ManagerAction update}catch{$rejected=$true}
if(-not $rejected -or ($script:actions -join ',') -ne 'build'){throw 'Build failure stopped running services'}
function New-ManagedArtifact { $script:actions.Add('build'); return 'validated-artifact' }
$script:actions.Clear()
Invoke-ManagerAction update
if(($script:actions -join ',') -ne 'build,stop,start:validated-artifact'){throw 'Wrong whole-runtime update order'}
Write-Output 'PASS'
'''
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', script],
                            env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER),
                                 'MANAGER_TEST_DIRECTORY': str(tmp_path)},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout

@pytest.mark.skipif(os.name != 'nt', reason='Windows orphan admission')
@pytest.mark.parametrize('candidate', ['registered', 'unknown', 'worker', 'connector'])
def test_dead_supervisor_never_allows_start_over_live_or_unknown_children(candidate):
    script = r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
function Get-Process {param($Id,$ErrorAction);if($env:ORPHAN_TEST -eq 'registered'){return [pscustomobject]@{StartTime=[datetime]'2026-01-01T00:00:00Z'}}}
function Get-CimInstance {
    param($ClassName,$Filter,$ErrorAction)
    if($env:ORPHAN_TEST -eq 'unknown'){return [pscustomobject]@{Name='python.exe';CommandLine=$null}}
    if($env:ORPHAN_TEST -eq 'worker'){return [pscustomobject]@{Name='python.exe';CommandLine='python.exe -m scripts.run_line_worker'}}
    if($env:ORPHAN_TEST -eq 'connector'){return [pscustomobject]@{Name='cloudflared.exe';CommandLine='cloudflared tunnel run'}}
}
function Stop-Process {throw 'Forbidden unqualified process stop'}
$state=[pscustomobject]@{roots=@([pscustomobject]@{pid=123;start_time='2026-01-01T00:00:00Z'})}
$rejected=$false
try{Assert-NoRemainingRuntime $state}catch{$rejected=$true}
if(-not $rejected){throw 'Unconfirmed old runtime accepted'}
Write-Output 'PASS'
'''
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', script],
                            env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER), 'ORPHAN_TEST': candidate},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout

@pytest.mark.skipif(os.name != 'nt', reason='Native Windows manager')
def test_status_with_inaccessible_or_null_process_start_time_does_not_crash(tmp_path):
    script = r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$ProjectRoot = 'C:\project\root'
$runtimeDirectory = $env:MANAGER_TEST_DIRECTORY
$statePath = Join-Path $runtimeDirectory 'state.json'
[void][IO.Directory]::CreateDirectory($runtimeDirectory)

# Mock Get-Process to return a process whose StartTime is $null (like System PID 4 or access denied)
function Get-Process {
    param($Id,$ErrorAction)
    return [pscustomobject]@{ Id = $Id; StartTime = $null }
}

# 1. State from another installation with inaccessible process
$foreignState = @{
    contract = 'windows-frontend-control/v1'
    project_root = 'C:\other\installation'
    supervisor_pid = 4
    supervisor_start_time = '2026-01-01T00:00:00Z'
    api_port = 8000
    react_port = 5173
} | ConvertTo-Json
Set-Content -LiteralPath $statePath -Value $foreignState -Encoding utf8
$state = Get-ManagedState
if ($null -ne $state) { throw 'Foreign stale state was not cleaned up' }
if (Test-Path -LiteralPath $statePath) { throw 'Foreign stale state file was not removed' }

# 2. Status output with inaccessible root processes
$matchingState = @{
    contract = 'windows-frontend-control/v1'
    project_root = 'C:\project\root'
    supervisor_pid = 123
    supervisor_start_time = '2026-01-01T00:00:00Z'
    api_port = 8000
    react_port = 5173
    roots = @(
        @{ label = 'FastAPI'; pid = 4; start_time = '2026-01-01T00:00:00Z' }
    )
} | ConvertTo-Json
Set-Content -LiteralPath $statePath -Value $matchingState -Encoding utf8
function Get-RemoteDisplayUrl { return 'http://localhost/' }
Show-ManagedStatus

Write-Output 'PASS'
'''
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', script],
                            env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER),
                                 'MANAGER_TEST_DIRECTORY': str(tmp_path)},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows manager')
def test_stop_and_status_accepts_normalized_project_root_variations(tmp_path):
    script = r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MANAGER_TEST_PATH,[ref]$tokens,[ref]$errors)
foreach($fn in $ast.FindAll({param($node)$node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$ProjectRoot = 'C:\project\root'
$runtimeDirectory = $env:MANAGER_TEST_DIRECTORY
$statePath = Join-Path $runtimeDirectory 'state.json'
[void][IO.Directory]::CreateDirectory($runtimeDirectory)

$simulatedStartTime = (Get-Date).ToUniversalTime().ToString('o')
function Get-Process {
    param($Id,$ErrorAction)
    return [pscustomobject]@{ Id = $Id; StartTime = [datetime]$simulatedStartTime }
}

# 1. State with trailing slash in project_root and live supervisor
$stateWithSlash = @{
    contract = 'windows-frontend-control/v1'
    project_root = 'C:\project\root\'
    supervisor_pid = 999
    supervisor_start_time = $simulatedStartTime
    api_port = 8000
    react_port = 5173
} | ConvertTo-Json
Set-Content -LiteralPath $statePath -Value $stateWithSlash -Encoding utf8

$state = Get-ManagedState
if ($null -eq $state) { throw 'State with trailing slash was rejected' }
if ($state.project_root -ne 'C:\project\root\') { throw 'State was mutated incorrectly' }

# 2. Stop-ManagedRuntime does not throw another installation error
$script:stopInvokedWithRoot = $null
$supervisorPath = 'fake_supervisor.ps1'
function powershell.exe {
    param([Parameter(ValueFromRemainingArguments=$true)]$AllArgs)
    $idx = [array]::IndexOf($AllArgs, '-ProjectRoot')
    if ($idx -ge 0) { $script:stopInvokedWithRoot = $AllArgs[$idx + 1] }
    $global:LASTEXITCODE = 0
}
Stop-ManagedRuntime
if ($script:stopInvokedWithRoot -ne 'C:\project\root') { throw 'Stop was not forwarded with canonical root' }

Write-Output 'PASS'
'''
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', script],
                            env={**os.environ, 'MANAGER_TEST_PATH': str(MANAGER),
                                 'MANAGER_TEST_DIRECTORY': str(tmp_path)},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout
