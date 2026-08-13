@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [ERROR] Missing project Python: "%PYTHON%"
  pause
  exit /b 2
)
if /I "%~1"=="--dry-run" (
  "%PYTHON%" -m scripts.launcher_preflight --profile database-reset
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  exit /b !DRY_RUN_EXIT!
)
if not "%~1"=="" (
  "%PYTHON%" -m scripts.reset_fake_database %*
  exit /b %ERRORLEVEL%
)
echo Previewing destructive reset of local union_db from the versioned template fixture...
"%PYTHON%" -m scripts.reset_fake_database
if errorlevel 1 (
  echo [ERROR] Reset preflight failed. Confirm .env targets local union_db and fixtures/db_snapshot_v2/v3 is complete.
  pause
  exit /b 1
)
echo.
echo Stop API, UI, monitor, and workers before continuing.
echo This deletes all current union_db data and loads the template test fixture.
set /p "RESET_CONFIRM=Type RESET to continue: "
if /I not "!RESET_CONFIRM!"=="RESET" (
  echo Cancelled. No database changes were requested.
  exit /b 0
)
"%PYTHON%" -m scripts.reset_fake_database --apply --confirm-database union_db
set "RESET_EXIT=!ERRORLEVEL!"
if not "!RESET_EXIT!"=="0" (echo [ERROR] Database reset failed with exit code !RESET_EXIT!.) else (echo Template database reset completed. Restart local services.)
pause
exit /b !RESET_EXIT!
