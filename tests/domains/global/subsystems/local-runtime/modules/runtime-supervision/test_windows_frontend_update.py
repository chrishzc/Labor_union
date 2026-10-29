"""Frontend maintenance must preserve every unrelated running service, without DB."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import shutil
import socket
from urllib.request import urlopen

import pytest

from scripts.build_react_admin_artifact import build_artifact

ROOT = Path(__file__).resolve().parents[7]
SUPERVISOR = ROOT / 'scripts/launchers/supervise_local_runtime.ps1'
CONTROL = ROOT / 'scripts/launchers/windows_frontend_control.ps1'
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows process ownership')

LOAD_FUNCTIONS = r'''
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:SUPERVISOR_TEST_PATH,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Supervisor parse failed' }
foreach($function in $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)) { Invoke-Expression $function.Extent.Text }
. $env:CONTROL_TEST_PATH
$ProjectRoot=$env:FRONTEND_TEST_ROOT; $PythonPath=$env:FRONTEND_TEST_PYTHON
$ApiPort=[int]$env:FRONTEND_TEST_API_PORT; $ReactPort=[int]$env:FRONTEND_TEST_PORT
$script:Owned=[System.Collections.Generic.List[object]]::new()
$script:IdentityRegistry=[System.Collections.Generic.List[object]]::new()
$script:UnknownRootPids=[System.Collections.Generic.List[int]]::new()
$script:CleanupUnknown=$false; $script:Stopping=$false; $script:ExitCode=0
$script:RunId='frontend-test'; $script:RunStartedAt=[DateTime]::UtcNow
$script:RemoteFrontendControlEnabled=$true
'''


def artifacts(tmp_path):
    paths = []
    for name in ('previous', 'candidate'):
        source = tmp_path / (name + '-source')
        source.mkdir()
        (source / 'index.html').write_text(f'<div id="root"></div><p>{name}</p>', encoding='utf-8')
        output = tmp_path / 'scratch/windows-remote' / ('artifact-' + name)
        build_artifact(output, source=source)
        paths.append(output)
    # Any frontend import/open of DB or dotenv is a regression, even when no DB
    # happens to be available on the developer's machine.
    guard = tmp_path / 'import-guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text('''
import sys
def guard(event, args):
    if event == 'import' and (args[0].startswith(('infrastructure.mysql', 'mysql', 'pymysql', 'dotenv')) or args[0] == 'api.main'):
        raise RuntimeError('DB/API bootstrap forbidden in frontend maintenance')
    if event == 'open' and str(args[0]).replace('\\\\', '/').rsplit('/', 1)[-1] == '.env':
        raise RuntimeError('dotenv read forbidden in frontend maintenance')
sys.addaudithook(guard)
''', encoding='utf-8')
    return paths, guard


@pytest.mark.parametrize('startup_failure', [False, True])
def test_real_frontend_restart_or_rollback_preserves_other_children(tmp_path, startup_failure):
    paths, guard = artifacts(tmp_path)
    requests = []

    class AuthGate(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200 if startup_failure and len(requests) == 2 else 401)
            self.send_header('Content-Length', '0')
            self.end_headers()

        def log_message(self, *args):
            pass

    import socket
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        frontend_port = reservation.getsockname()[1]
    with ThreadingHTTPServer(('127.0.0.1', 0), AuthGate) as api:
        thread = threading.Thread(target=api.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run([
                str(POWERSHELL), '-NoProfile', '-Command', LOAD_FUNCTIONS + r'''
try {
    foreach($label in @('FastAPI','Runtime Monitor','Cloudflare Tunnel')) {
        [void](Start-Owned -Label $label -FilePath $PythonPath -ArgumentList @('-c','"import time; time.sleep(120)"'))
    }
    $preserved=@($script:Owned)
    [void](Start-RemoteFrontendChild $env:PREVIOUS_ARTIFACT_TEST)
    $previousPid=@($script:Owned | Where-Object Label -eq 'Remote React')[0].Pid
    $result=Invoke-RemoteFrontendRestart $env:CANDIDATE_ARTIFACT_TEST
    $expected=if($env:FAIL_STARTUP_TEST -eq '1'){'rolled_back'}else{'updated'}
    if($result.status -ne $expected){throw ('Unexpected outcome: '+($result|ConvertTo-Json))}
    foreach($entry in $preserved){if(-not(Test-OwnedAlive $entry)){throw 'Unrelated service was stopped'}}
    $frontend=@($script:Owned | Where-Object Label -eq 'Remote React')[0]
    if($frontend.Pid -eq $previousPid){throw 'Frontend was not restarted'}
    $body=(Invoke-WebRequest "http://127.0.0.1:$ReactPort/test/" -UseBasicParsing).Content
    if($expected -eq 'updated' -and $body -notmatch 'candidate'){throw 'Wrong frontend content'}
    if($expected -eq 'rolled_back' -and $body -notmatch 'previous'){throw 'Rollback content missing'}
    $before=$frontend.Pid
    [IO.File]::AppendAllText((Join-Path $env:CANDIDATE_ARTIFACT_TEST 'index.html'),'tampered')
    $rejected=$false
    try{[void](Invoke-RemoteFrontendRestart $env:CANDIDATE_ARTIFACT_TEST)}catch{$rejected=$true}
    if(-not $rejected){throw 'Corrupt artifact accepted'}
    if(@($script:Owned|Where-Object Label -eq 'Remote React')[0].Pid -ne $before){throw 'Validation failure restarted frontend'}
    foreach($entry in $preserved){if(-not(Test-OwnedAlive $entry)){throw 'Validation failure stopped unrelated service'}}
    Write-Output 'PASS'
} finally { Stop-OwnedProcessTrees }
'''], cwd=ROOT, env={**os.environ,
                'SUPERVISOR_TEST_PATH': str(SUPERVISOR), 'CONTROL_TEST_PATH': str(CONTROL),
                'FRONTEND_TEST_ROOT': str(tmp_path), 'FRONTEND_TEST_PYTHON': sys.executable,
                'FRONTEND_TEST_API_PORT': str(api.server_port), 'FRONTEND_TEST_PORT': str(frontend_port),
                'PREVIOUS_ARTIFACT_TEST': str(paths[0]), 'CANDIDATE_ARTIFACT_TEST': str(paths[1]),
                'FAIL_STARTUP_TEST': '1' if startup_failure else '0',
                'PYTHONPATH': os.pathsep.join((str(guard), str(ROOT))),
            }, capture_output=True, text=True, timeout=110)
        finally:
            api.shutdown()
            thread.join(timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout
    assert requests == ['/api/v1/admin/auth/me'] * (3 if startup_failure else 2)


def test_stale_control_request_and_changed_process_identity_never_stop_children(tmp_path):
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', LOAD_FUNCTIONS + r'''
$directory=Get-FrontendControlDirectory
[void][IO.Directory]::CreateDirectory($directory)
$id='a'*32
Write-FrontendControlJson (Join-Path $directory 'request.json') @{id=$id;run_id='other-run';operation='restart_frontend';artifact_path='unused'}
function Invoke-RemoteFrontendRestart { throw 'Should not reach restart' }
Receive-FrontendControlRequest
$response=Get-Content -Raw (Join-Path $directory ($id+'.response.json'))|ConvertFrom-Json
if($response.status -ne 'rejected'){throw 'Stale request accepted'}
function Refresh-OwnedIdentityRegistry {}
function Get-ProcessSnapshot {return [pscustomobject]@{State='alive';StartTime=[datetime]'2026-01-02T00:00:00Z';Process=$null}}
$entry=[pscustomobject]@{Label='Remote React';Pid=123;RootPid=123;StartTime=[datetime]'2026-01-01T00:00:00Z';IsRoot=$true}
$script:IdentityRegistry.Add($entry)
$rejected=$false
try{Stop-RemoteFrontendChild $entry}catch{$rejected=$true}
if(-not $rejected){throw 'Changed PID creation time accepted'}
Write-Output 'PASS'
'''], cwd=ROOT, env={**os.environ,
        'SUPERVISOR_TEST_PATH': str(SUPERVISOR), 'CONTROL_TEST_PATH': str(CONTROL),
        'FRONTEND_TEST_ROOT': str(tmp_path), 'FRONTEND_TEST_PYTHON': sys.executable,
        'FRONTEND_TEST_API_PORT': '8000', 'FRONTEND_TEST_PORT': '5173',
    }, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout


def test_live_legacy_handoff_and_repeated_frontend_updates_do_not_restart_other_services(tmp_path):
    paths, guard = artifacts(tmp_path)
    launcher_dir = tmp_path / 'scripts/launchers'
    launcher_dir.mkdir(parents=True)
    (tmp_path / 'scripts/__init__.py').write_text(
        f'__path__.append({str(ROOT / "scripts")!r})\n', encoding='utf-8',
    )
    (tmp_path / 'scripts/run_service_monitor.py').write_text('import time; time.sleep(180)\n', encoding='utf-8')
    (tmp_path / 'scripts/fake_tunnel.py').write_text('import time; time.sleep(180)\n', encoding='utf-8')
    (tmp_path / 'api').mkdir()
    (tmp_path / 'api/__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'api/main.py').write_text('''
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
async def auth(request): return Response(status_code=401)
app=Starlette(routes=[Route('/api/v1/admin/auth/me',auth)])
''', encoding='utf-8')
    with socket.socket() as a, socket.socket() as b:
        a.bind(('127.0.0.1', 0)); b.bind(('127.0.0.1', 0))
        api_port, frontend_port = a.getsockname()[1], b.getsockname()[1]
    legacy_path = launcher_dir / SUPERVISOR.name
    legacy_path.write_text(r'''
param($ProjectRoot,$PythonPath,[int]$ApiPort,[int]$ReactPort)
$ErrorActionPreference='Stop'
$env:ACCESS_CONTROL_PROFILE='production'; $env:ENABLE_ADMIN_AUTH='true'
$env:WINDOWS_REMOTE_API_PORT="$ApiPort"; $env:WINDOWS_REMOTE_ARTIFACT_DIR=$env:PREVIOUS_ARTIFACT_TEST
$roots=@()
foreach($item in @(
    @('FastAPI',"-m uvicorn api.main:app --host 127.0.0.1 --port $ApiPort"),
    @('Remote React',"-m uvicorn scripts.windows_remote_runtime:create_app --factory --host 127.0.0.1 --port $ReactPort --no-proxy-headers"),
    @('Runtime Monitor','-m scripts.run_service_monitor'),
    @('Cloudflare Tunnel','-m scripts.fake_tunnel --token-file synthetic-token-path')
)) {
    $child=Start-Process -FilePath $PythonPath -ArgumentList $item[1] -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    $roots+=@{label=$item[0];pid=$child.Id;start_time=$child.StartTime.ToUniversalTime().ToString('o')}
}
$roots|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $ProjectRoot 'legacy-children.json')
try{while($true){Start-Sleep -Seconds 1}}
finally{'old cleanup must not run'|Set-Content (Join-Path $ProjectRoot 'legacy-finally.txt')}
''', encoding='utf-8')
    environment = {**os.environ, 'PREVIOUS_ARTIFACT_TEST': str(paths[0]),
                   'PYTHONPATH': os.pathsep.join((str(tmp_path), str(ROOT)))}
    process = subprocess.Popen([
        str(POWERSHELL), '-NoProfile', '-File', str(legacy_path), '-ProjectRoot', str(tmp_path),
        '-PythonPath', sys.executable, '-ApiPort', str(api_port), '-ReactPort', str(frontend_port),
    ], cwd=tmp_path, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    control_dir = tmp_path / 'scratch/windows-remote/frontend-control'
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urlopen(f'http://127.0.0.1:{frontend_port}/test/', timeout=1) as response:
                    assert b'previous' in response.read()
                break
            except OSError:
                assert process.poll() is None, 'Legacy fixture exited early'
                assert time.monotonic() < deadline, 'Legacy frontend fixture did not start'
                time.sleep(.2)
        originals = json.loads((tmp_path / 'legacy-children.json').read_text(encoding='utf-8-sig'))
        control_dir.mkdir(parents=True, exist_ok=True)
        # An older frontend-capable supervisor is not current merely because its
        # PID is alive: source updates require the tested controller revision.
        (control_dir / 'state.json').write_text(json.dumps({
            'contract': 'windows-frontend-control/v1', 'run_id': 'legacy-controller',
            'supervisor_pid': process.pid, 'supervisor_start_time': '',
            'project_root': str(tmp_path), 'api_port': api_port, 'react_port': frontend_port,
        }), encoding='utf-8')
        timestamp = subprocess.check_output([
            str(POWERSHELL), '-NoProfile', '-Command',
            f"(Get-Process -Id {process.pid}).StartTime.ToUniversalTime().ToString('o')",
        ], text=True).strip()
        legacy_state = json.loads((control_dir / 'state.json').read_text())
        legacy_state['supervisor_start_time'] = timestamp
        (control_dir / 'state.json').write_text(json.dumps(legacy_state), encoding='utf-8')
        shutil.copyfile(SUPERVISOR, legacy_path)
        shutil.copyfile(CONTROL, launcher_dir / CONTROL.name)
        environment['PYTHONPATH'] = os.pathsep.join((str(guard), str(tmp_path), str(ROOT)))
        for _ in range(2):
            result = subprocess.run([
                str(POWERSHELL), '-NoProfile', '-File', str(legacy_path), '-ProjectRoot', str(tmp_path),
                '-PythonPath', sys.executable, '-ApiPort', str(api_port), '-ReactPort', str(frontend_port),
                '-FrontendArtifact', str(paths[1]),
            ], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=110)
            assert result.returncode == 0, result.stdout + result.stderr + '\n' + '\n'.join(
                p.read_text(encoding='utf-8-sig') for p in control_dir.glob('*.stderr.log'))
            state = json.loads((control_dir / 'state.json').read_text(encoding='utf-8-sig'))
            preserved = [root for root in originals if root['label'] != 'Remote React']
            assert {r['label']: (r['pid'], r['start_time']) for r in state['roots'] if r['label'] != 'Remote React'} == {
                r['label']: (r['pid'], r['start_time']) for r in preserved}
            with urlopen(f'http://127.0.0.1:{frontend_port}/test/', timeout=3) as response:
                assert b'candidate' in response.read()
        assert len(list(control_dir.glob('adoption-*.json'))) == 2  # snapshot plus standby acknowledgement
        assert not (tmp_path / 'legacy-finally.txt').exists()
        # The same verified supervisor now supports stopping the ENTIRE group.
        # All children above are isolated fake services; no provider cycle runs.
        stopped = subprocess.run([
            str(POWERSHELL), '-NoProfile', '-File', str(legacy_path), '-ProjectRoot', str(tmp_path),
            '-PythonPath', sys.executable, '-ApiPort', str(api_port), '-ReactPort', str(frontend_port),
            '-StopRuntime',
        ], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        terminal = json.loads((control_dir / 'state.json').read_text(encoding='utf-8-sig'))
        assert terminal['runtime_status'] == 'stopped'
        assert terminal['cleanup_confirmed'] is True
        with pytest.raises(OSError):
            urlopen(f'http://127.0.0.1:{frontend_port}/test/', timeout=1)
    finally:
        # Only fixture identities captured in these files may be stopped.
        cleanup = LOAD_FUNCTIONS + r'''
$statePath=Join-Path (Get-FrontendControlDirectory) 'state.json'
if(Test-Path $statePath){
    $state=Get-Content -Raw $statePath|ConvertFrom-Json
    $owner=Get-ProcessSnapshot $state.supervisor_pid
    $roots=@($state.roots)
    if($owner.State -eq 'alive' -and (Test-SameProcessIdentity ([pscustomobject]@{StartTime=[datetime]$state.supervisor_start_time}) $owner)){
        foreach($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($state.supervisor_pid)")){
            if($child.CommandLine -like '*uvicorn scripts.windows_remote_runtime:create_app*'){
                $snapshot=Get-ProcessSnapshot $child.ProcessId
                if($snapshot.State -eq 'alive'){$roots+=@{label='Remote React';pid=$child.ProcessId;start_time=$snapshot.StartTime.ToUniversalTime().ToString('o')}}
            }
        }
        $owner.Process.Kill();[void]$owner.Process.WaitForExit(5000)
    }
}else{$roots=@()}
$old=Join-Path $ProjectRoot 'legacy-children.json'
if(Test-Path $old){$oldRoots=Get-Content -Raw $old|ConvertFrom-Json; $roots+=@($oldRoots)}
foreach($root in $roots){
    $snapshot=Get-ProcessSnapshot $root.pid
    if($snapshot.State -ne 'alive' -or -not(Test-SameProcessIdentity ([pscustomobject]@{StartTime=[datetime]$root.start_time}) $snapshot)){continue}
    $entry=[pscustomobject]@{Label=$root.label;Pid=[int]$root.pid;StartTime=$snapshot.StartTime;Process=$snapshot.Process;ExitCode=$null}
    $script:Owned.Add($entry)
    [void](Add-Identity -ProcessId $entry.Pid -StartTime $entry.StartTime -Label $entry.Label -RootPid $entry.Pid -IsRoot $true -Process $entry.Process)
}
Stop-OwnedProcessTrees
'''
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        cleaned = subprocess.run([str(POWERSHELL), '-NoProfile', '-Command', cleanup], cwd=ROOT,
            env={**os.environ, 'SUPERVISOR_TEST_PATH': str(SUPERVISOR), 'CONTROL_TEST_PATH': str(CONTROL),
                 'FRONTEND_TEST_ROOT': str(tmp_path), 'FRONTEND_TEST_PYTHON': sys.executable,
                 'FRONTEND_TEST_API_PORT': str(api_port), 'FRONTEND_TEST_PORT': str(frontend_port)},
            capture_output=True, text=True, timeout=40)
        assert cleaned.returncode == 0, cleaned.stdout + cleaned.stderr
