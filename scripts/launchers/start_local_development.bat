@echo off
goto :MAIN
@REM File: start_local_development.bat
@REM Description: 驗證本機 DB readiness 後啟動 FastAPI、React/Vite、monitor 與 workers。
@REM Source archives must preserve CRLF so cmd.exe can resolve CALL labels.
:MAIN
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%CD%"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PY=%CD%\.venv\Scripts\python.exe"
if /I "%~1"=="--dry-run" (
    if not exist "%PY%" (
        echo [ERROR] Virtual environment .venv not found.
        exit /b 1
    )
    "%PY%" -m scripts.launcher_preflight --profile local-windows
    set "DRY_RUN_EXIT=!ERRORLEVEL!"
    if not "!DRY_RUN_EXIT!"=="0" exit /b !DRY_RUN_EXIT!
    "%PY%" -m scripts.check_runtime_database --dry-run
    set "DRY_RUN_EXIT=!ERRORLEVEL!"
    if not "!DRY_RUN_EXIT!"=="0" exit /b !DRY_RUN_EXIT!
    "%PY%" -m scripts.launcher_preflight --profile dual-run
    set "DRY_RUN_EXIT=!ERRORLEVEL!"
    if /I "%REACT_ADMIN_RUNTIME_PROFILE%"=="artifact-runtime" (
        if not "!DRY_RUN_EXIT!"=="0" exit /b !DRY_RUN_EXIT!
        "%PY%" -m scripts.launcher_preflight --profile artifact-runtime
        set "DRY_RUN_EXIT=!ERRORLEVEL!"
    )
    exit /b !DRY_RUN_EXIT!
)
if /I "%~1"=="--smoke-test" goto :SMOKE_TEST
if /I "%~1"=="--artifact-runtime-smoke" goto :ARTIFACT_RUNTIME_SMOKE
echo ==========================================
echo Labor Union Local Development Startup Script
echo ==========================================
if /I "%REACT_ADMIN_RUNTIME_PROFILE%"=="artifact-runtime" (
    "%PY%" -m scripts.launcher_preflight --profile artifact-runtime
    if errorlevel 1 exit /b !ERRORLEVEL!
)

:: 2. Set Python path
echo [Step 1] Setting Python environment...
if not exist .venv\Scripts\python.exe (
    echo [Error] Virtual environment .venv not found. Please install dependencies first.
    pause
    exit /b 1
)
echo [Step 2] Checking configured MySQL connection and schema, read-only...
"%PY%" -m scripts.check_runtime_database
set "READINESS_EXIT=!ERRORLEVEL!"
if !READINESS_EXIT! neq 0 (
    echo [Error] MySQL readiness failed. Check DB_* settings and provision the target schema separately.
    pause
    exit /b !READINESS_EXIT!
)

echo [Step 3] Launching Docker Compose Redis...
docker compose up -d redis
set "DOCKER_EXIT=!ERRORLEVEL!"
if not "!DOCKER_EXIT!"=="0" (
    echo [Error] Failed to start Redis through Docker Compose.
    pause
    exit /b !DOCKER_EXIT!
)

echo ==========================================
echo Database connection and schema ready! Starting services...
echo ==========================================
echo [Notice] start_local_development.bat is for local development only; it is not a production deployment entrypoint.
echo [Notice] Production readiness validation is intentionally not run by this development launcher.

:: 4. Supervise all local runtime children in one owned process tree.
echo [Step 4] Starting owned Windows runtime supervision...
@REM supervise_local_runtime.ps1 owns api.main:app, React/Vite, monitor and workers.
@REM artifact-runtime uses --react-admin-health-check inside the supervisor after API readiness.
@REM Static lifecycle order: start "FastAPI Server" -> call :WAIT_FOR_HTTP "http://127.0.0.1:8000/health"
@REM then start "React Admin UI" -> call :WAIT_FOR_HTTP "http://127.0.0.1:5173/admin/" -> start "LINE Worker".
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0supervise_local_runtime.ps1" -ProjectRoot "%PROJECT_ROOT%" -PythonPath "%PY%" -ApiPort 8000 -ReactPort 5173
set "SUPERVISOR_EXIT=!ERRORLEVEL!"
if not "!SUPERVISOR_EXIT!"=="0" (
    echo [Error] Local runtime supervision stopped with exit code !SUPERVISOR_EXIT!.
    echo [Action] Keep this window open and copy the final RUNTIME_EVENT or worker error.
    pause
    exit /b !SUPERVISOR_EXIT!
)
echo [Ready] Local runtime supervision ended cleanly.
exit /b 0

:SMOKE_TEST
echo [Smoke] Phase5B GET-only dual-run; Docker, DB, monitor and workers disabled.
"%PY%" -m scripts.smoke_local_development_launcher
exit /b !ERRORLEVEL!

:ARTIFACT_RUNTIME_SMOKE
echo [Smoke] Phase6B-RUN artifact health only; no child, Docker, DB, provider or observation write.
"%PY%" -m scripts.smoke_local_development_launcher --artifact-runtime
exit /b !ERRORLEVEL!
