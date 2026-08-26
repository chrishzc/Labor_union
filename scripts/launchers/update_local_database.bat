rem File: update_local_database.bat
rem Description: Validates local database update wiring and runs qualified additive only after confirmation.
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
  exit /b !ERRORLEVEL!
)
if not "%~1"=="" (
  "%PYTHON%" -m scripts.update_local_database %*
  exit /b %ERRORLEVEL%
)
echo Previewing the qualified local additive update for the database configured in .env...
"%PYTHON%" -m scripts.update_local_database
if errorlevel 1 (
  echo [ERROR] Database update preflight failed. Review the reported schema state before retrying.
  pause
  exit /b 1
)
echo.
echo The default apply is additive-only and does not create a candidate or replace the source.
echo Use --strategy replacement --allow-long-run only for the separately approved long-running route.
set /p "UPDATE_CONFIRM=Type UPDATE to continue: "
if /I not "!UPDATE_CONFIRM!"=="UPDATE" (
  echo Cancelled. No database changes were requested.
  exit /b 0
)
"%PYTHON%" -m scripts.update_local_database --apply --confirm-configured-database
set "UPDATE_EXIT=!ERRORLEVEL!"
if not "!UPDATE_EXIT!"=="0" (echo [ERROR] Database update failed with exit code !UPDATE_EXIT!.) else (echo Database additive update completed. Restart local services if the release requires it.)
pause
exit /b !UPDATE_EXIT!
