@echo off
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

:: 2. Activate Virtual Environment
echo [Step 2] Activating Python virtual environment...
if not exist .venv\Scripts\activate.bat (
    echo [Error] Virtual environment .venv not found. Please install dependencies first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat

:: 3. Wait for database
echo [Step 3] Waiting for MySQL database to become ready...
python scripts/wait_for_db.py
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
start "FastAPI Server" cmd /k "call .venv\Scripts\activate.bat && uvicorn api.main:app --reload --port 8000"

echo [Step 5] Launching Streamlit interface...
start "Streamlit Client UI" cmd /k "call .venv\Scripts\activate.bat && streamlit run ui/app.py"

echo [Step 6] Launching File Watcher Service...
start "File Watcher" cmd /k "call .venv\Scripts\activate.bat && python scripts/file_watcher.py"

echo ==========================================
echo Lobar Union System online services are running!
echo - API Docs: http://127.0.0.1:8000/docs
echo - Streamlit UI: http://localhost:8501
echo - File Watcher: Monitoring downloads/ folder
echo ==========================================
pause
