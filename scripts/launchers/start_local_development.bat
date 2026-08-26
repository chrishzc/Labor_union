@echo off
goto :MAIN
@REM File: start_local_development.bat
@REM Description: 驗證本機 DB readiness 後啟動 FastAPI、React/Vite、monitor 與 workers。
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

:: 1. Launch Docker Compose
echo [Step 1] Launching Docker Compose (MySQL 8.0)...
docker-compose up -d
if %errorlevel% neq 0 (
    echo [Error] Failed to start Docker Compose! Please check if Docker Desktop is running.
    pause
    exit /b %errorlevel%
)

:: 2. Set Python path
echo [Step 2] Setting Python environment...
if not exist .venv\Scripts\python.exe (
    echo [Error] Virtual environment .venv not found. Please install dependencies first.
    pause
    exit /b 1
)
:: 3. Wait for database
echo [Step 3] Waiting for MySQL database to become ready...
"%PY%" scripts/wait_for_db.py
if %errorlevel% neq 0 (
    echo [Error] Database connection timeout!
    pause
    exit /b %errorlevel%
)

echo [Step 4] Verifying the local database schema release...
"%PY%" -m scripts.update_local_database --require-current
set "READINESS_EXIT=!ERRORLEVEL!"
if !READINESS_EXIT! neq 0 (
    echo [Error] Local database schema is not current. Run scripts\launchers\update_local_database.bat first.
    pause
    exit /b !READINESS_EXIT!
)

echo ==========================================
echo Database connection and schema ready! Starting services...
echo ==========================================
echo [Notice] start_local_development.bat is for local development only; it is not a production deployment entrypoint.
echo [Notice] Production readiness validation is intentionally not run by this development launcher.

call :ENSURE_INTERNAL_SERVICE_KEY
if errorlevel 1 exit /b !ERRORLEVEL!

:: 4. Launch servers concurrently
echo [Step 5] Launching FastAPI server...
start "FastAPI Server" cmd /k ""%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
call :WAIT_FOR_HTTP "http://127.0.0.1:8000/health" "FastAPI"
if errorlevel 1 exit /b !ERRORLEVEL!
if /I "%REACT_ADMIN_RUNTIME_PROFILE%"=="artifact-runtime" (
    "%PY%" -m scripts.run_service_monitor --react-admin-health-check
    if errorlevel 1 exit /b !ERRORLEVEL!
)

echo [Step 6] Launching React/Vite interface...
start "React Admin UI" /D "%CD%\ui_react" cmd /k "npm.cmd run dev -- --host 0.0.0.0 --port 5173 --strictPort"
call :WAIT_FOR_HTTP "http://127.0.0.1:5173/admin/" "React/Vite"
if errorlevel 1 exit /b !ERRORLEVEL!

"%PY%" -m scripts.launcher_preflight --profile line-worker >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [Step 7] Launching independent LINE Worker...
    start "LINE Worker" cmd /k ""%PY%" -m scripts.run_line_worker"
) else (
    echo [Step 7] Skipping LINE Worker: local LINE credentials or runtime configuration are unavailable.
)

echo [Step 8] Launching active runtime monitor...
start "Runtime Monitor" cmd /k ""%PY%" -m scripts.run_service_monitor"

echo [Step 9] Launching Durable Background Worker...
start "Durable Background Worker" cmd /k ""%PY%" -m scripts.run_durable_job_worker"

echo [Step 10] Launching Incident Maintenance Worker...
start "Incident Maintenance Worker" cmd /k ""%PY%" -m scripts.run_incident_worker"

findstr /R /B /I "^KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED=true" "%CD%\.env" >nul
if %errorlevel% equ 0 (
    echo [Step 11] Launching Knowledge Retrieval Worker...
    start "Knowledge Retrieval Worker" cmd /k ""%PY%" -m scripts.run_knowledge_worker"
)

echo ==========================================
echo Lobar Union System online services are running!
echo - API Docs: http://127.0.0.1:8000/docs
echo - React UI: http://localhost:5173/admin/
echo - LINE Worker: independent durable queue consumer
echo - Runtime Monitor: active health probes and alert projection
echo - Durable Background Worker: independently processes background jobs
echo ==========================================
pause
exit /b 0

:SMOKE_TEST
echo [Smoke] Phase5B GET-only dual-run; Docker, DB, monitor and workers disabled.
"%PY%" -m scripts.smoke_local_development_launcher
exit /b !ERRORLEVEL!

:ARTIFACT_RUNTIME_SMOKE
echo [Smoke] Phase6B-RUN artifact health only; no child, Docker, DB, provider or observation write.
"%PY%" -m scripts.smoke_local_development_launcher --artifact-runtime
exit /b !ERRORLEVEL!

:ENSURE_INTERNAL_SERVICE_KEY
if not defined APP_ENV set "APP_ENV=development"
if defined INTERNAL_SERVICE_SHARED_KEY exit /b 0
for /f "delims=" %%K in ('powershell.exe -NoProfile -NonInteractive -Command "$bytes = New-Object byte[] 32; $random = [Security.Cryptography.RandomNumberGenerator]::Create(); $random.GetBytes($bytes); $random.Dispose(); [Convert]::ToBase64String($bytes)"') do set "INTERNAL_SERVICE_SHARED_KEY=%%K"
if defined INTERNAL_SERVICE_SHARED_KEY exit /b 0
echo [Error] Failed to generate the local internal service key.
exit /b 1

:WAIT_FOR_HTTP
set "WAIT_URL=%~1"
set "WAIT_SERVICE=%~2"
for /L %%A in (1,1,30) do (
    "%PY%" -c "from urllib.request import urlopen; response = urlopen(__import__('sys').argv[1], timeout=2); raise SystemExit(0 if response.status == 200 else 1)" "!WAIT_URL!" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo [Ready] !WAIT_SERVICE! is accepting requests.
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)
echo [Error] !WAIT_SERVICE! did not become ready: !WAIT_URL!
exit /b 1
