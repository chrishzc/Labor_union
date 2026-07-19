@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ==========================================
echo Lobar Union System Online Startup Script
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
set "PY=%CD%\.venv\Scripts\python.exe"

:: 3. Wait for database
echo [Step 3] Waiting for MySQL database to become ready...
"%PY%" scripts/wait_for_db.py
if %errorlevel% neq 0 (
    echo [Error] Database connection timeout!
    pause
    exit /b %errorlevel%
)

echo ==========================================
echo Database connection ready! Starting services...
echo ==========================================

:: 4. Launch servers concurrently
echo [Step 4] Launching FastAPI server...
start "FastAPI Server" cmd /k ""%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

echo [Step 5] Launching Streamlit interface...
start "Streamlit Client UI" cmd /k ""%PY%" -m streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501"

echo [Step 6] Launching File Watcher Service...
start "File Watcher" cmd /k ""%PY%" scripts/file_watcher.py"

echo ==========================================
echo Lobar Union System online services are running!
echo - API Docs: http://127.0.0.1:8000/docs
echo - Streamlit UI: http://localhost:8501
echo - File Watcher: Monitoring downloads/ folder
echo ==========================================
pause
