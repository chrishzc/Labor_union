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
