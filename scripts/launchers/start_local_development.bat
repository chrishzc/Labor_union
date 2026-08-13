@REM File: start_local_development.bat
@REM Description: 驗證本機 DB readiness 後啟動 API、UI、monitor、watcher 與 workers。
@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%CD%"
chcp 65001 >nul
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
    exit /b !DRY_RUN_EXIT!
)
if /I "%~1"=="--smoke-test" goto :SMOKE_TEST
echo ==========================================
echo Labor Union Local Development Startup Script
echo ==========================================

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

:: 4. Launch servers concurrently
echo [Step 5] Launching FastAPI server...
start "FastAPI Server" cmd /k ""%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

"%PY%" -m scripts.launcher_preflight --profile line-worker >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [Step 6] Launching independent LINE Worker...
    start "LINE Worker" cmd /k ""%PY%" -m scripts.run_line_worker"
) else (
    echo [Step 6] Skipping LINE Worker: local LINE credentials or runtime configuration are unavailable.
)

echo [Step 7] Launching Streamlit interface...
start "Streamlit Client UI" cmd /k ""%PY%" -m streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501"

echo [Step 8] Launching active runtime monitor...
start "Runtime Monitor" cmd /k ""%PY%" -m scripts.run_service_monitor"

echo [Step 9] Launching File Watcher Service...
start "File Watcher" cmd /k ""%PY%" scripts/file_watcher.py"

echo [Step 10] Launching Durable Background Worker...
start "Durable Background Worker" cmd /k ""%PY%" -m scripts.run_durable_job_worker"

findstr /R /B /I "^KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED=true" "%CD%\.env" >nul
if %errorlevel% equ 0 (
    echo [Step 11] Launching Knowledge Retrieval Worker...
    start "Knowledge Retrieval Worker" cmd /k ""%PY%" -m scripts.run_knowledge_worker"
)

echo ==========================================
echo Lobar Union System online services are running!
echo - API Docs: http://127.0.0.1:8000/docs
echo - Streamlit UI: http://localhost:8501
echo - LINE Worker: independent durable queue consumer
echo - Runtime Monitor: active health probes and alert projection
echo - File Watcher: Monitoring downloads/ folder
echo - Durable Background Worker: independently processes background jobs
echo ==========================================
pause
exit /b 0

:SMOKE_TEST
echo [Smoke] Launching Docker Compose and waiting for MySQL...
docker-compose up -d
if errorlevel 1 exit /b !ERRORLEVEL!
"%PY%" scripts/wait_for_db.py
if errorlevel 1 exit /b !ERRORLEVEL!
"%PY%" -m scripts.update_local_database --require-current
if errorlevel 1 exit /b !ERRORLEVEL!
"%PY%" -m scripts.smoke_local_development_launcher
exit /b !ERRORLEVEL!
