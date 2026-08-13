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
  "%PYTHON%" -m scripts.launcher_preflight --profile database-update
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  exit /b !DRY_RUN_EXIT!
)
if not "%~1"=="" (
  "%PYTHON%" -m scripts.update_local_database %*
  exit /b %ERRORLEVEL%
)
echo Previewing preserve-data update for the database configured in .env...
"%PYTHON%" -m scripts.update_local_database
if errorlevel 1 (
  echo [ERROR] Database update preflight failed. Review the reported schema state before retrying.
  pause
  exit /b 1
)
echo.
echo Stop API, UI, monitor, and workers before continuing.
echo A backup and verified candidate are created before union_db is replaced under the same name.
set /p "UPDATE_CONFIRM=Type UPDATE to continue: "
if /I not "!UPDATE_CONFIRM!"=="UPDATE" (
  echo Cancelled. No database changes were requested.
  exit /b 0
)
"%PYTHON%" -m scripts.update_local_database --apply --confirm-database union_db
set "UPDATE_EXIT=!ERRORLEVEL!"
if not "!UPDATE_EXIT!"=="0" (echo [ERROR] Database update failed with exit code !UPDATE_EXIT!.) else (echo Database update completed. Restart local services; union_db now contains the verified upgraded data.)
pause
exit /b !UPDATE_EXIT!
