@echo off
echo ==========================================
echo Lobar Union System Startup Script
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

:: 4. Initialize Database
echo [Step 4] Initializing database schema (schema.sql)...
python scripts/init_db.py
if %errorlevel% neq 0 (
    echo [Error] Database initialization failed!
    pause
    exit /b %errorlevel%
)

:: 5. Generate Fake Data (first pass - DB is still empty of staff/orders here,
::    so this call will only seed base fake data and will automatically skip
::    schedule allocation / order-status randomization. That step runs again
::    later in Step 10, after real data has been imported.)
echo [Step 5] Generating roster and finance fake data (initial pass, schedule allocation will be skipped until data is imported)...
python scripts/generate_fake_data.py
if %errorlevel% neq 0 (
    echo [Error] Fake data generation failed!
    pause
    exit /b %errorlevel%
)

:: 6. Import Data
echo [Step 6] Importing client HCM data...
python scripts/imports/import_client_hcm.py
if %errorlevel% neq 0 (
    echo [Error] HCM import failed!
    pause
    exit /b %errorlevel%
)

echo [Step 7] Importing client BeClass data...
python scripts/imports/import_client_beclass.py
if %errorlevel% neq 0 (
    echo [Error] Client BeClass import failed!
    pause
    exit /b %errorlevel%
)

echo [Step 8] Importing caregiver BeClass data...
python scripts/imports/import_staff_beclass.py
if %errorlevel% neq 0 (
    echo [Error] Caregiver BeClass import failed!
    pause
    exit /b %errorlevel%
)

echo [Step 9] Importing finance payment data...
python scripts/imports/import_finance_excel.py
if %errorlevel% neq 0 (
    echo [Error] Finance import failed!
    pause
    exit /b %errorlevel%
)

:: 10. Re-run fake data generation now that staff/orders exist, so the
::     timeline-advancement algorithm can allocate caregivers and diversify
::     order statuses (in negotiation / in service / completed / cancelled).
echo [Step 10] Allocating caregiver schedules and diversifying order statuses...
python scripts/generate_fake_data.py
if %errorlevel% neq 0 (
    echo [Error] Schedule allocation failed!
    pause
    exit /b %errorlevel%
)

echo ==========================================
echo Initialization and import completed successfully!
echo ==========================================

:: 11. Launch servers concurrently
echo [Step 11] Launching FastAPI server...
start "FastAPI Server" cmd /k "call .venv\Scripts\activate.bat && uvicorn api.main:app --reload --port 8000"

echo [Step 12] Launching Streamlit interface...
start "Streamlit Client UI" cmd /k "call .venv\Scripts\activate.bat && streamlit run ui/app.py"

echo ==========================================
echo System is running in the background!
echo - API Docs: http://127.0.0.1:8000/docs
echo - Streamlit UI: http://localhost:8501
echo ==========================================
pause
