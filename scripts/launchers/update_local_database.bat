rem File: update_local_database.bat
rem Description: Runs qualified additive, or an explicitly confirmed preserve-data replacement fallback.
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
set "UPDATE_STRATEGY=additive"
"%PYTHON%" -m scripts.update_local_database
if errorlevel 1 (
  echo.
  echo Additive update is unavailable. Checking the preserve-data replacement route...
  "%PYTHON%" -m scripts.update_local_database --strategy replacement --allow-long-run
  if errorlevel 1 (
    echo [ERROR] Both additive and preserve-data replacement preflight failed. Review the reported schema state before retrying.
    pause
    exit /b 1
  )
  set "UPDATE_STRATEGY=replacement"
)
echo.
if /I "!UPDATE_STRATEGY!"=="replacement" goto CONFIRM_REPLACEMENT
echo The default apply is additive-only and does not create a candidate or replace the source.
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

:CONFIRM_REPLACEMENT
echo This route creates a preserve-data candidate, verifies it, and replaces the configured local source database.
echo A rollback dump and operation receipts will be retained under scratch/local_database_updates.
set /p "REPLACE_CONFIRM=Type REPLACE to continue: "
if /I not "!REPLACE_CONFIRM!"=="REPLACE" (
  echo Cancelled. No database changes were requested.
  exit /b 0
)
"%PYTHON%" -m scripts.update_local_database --strategy replacement --allow-long-run --apply --confirm-configured-database
set "UPDATE_EXIT=!ERRORLEVEL!"
if not "!UPDATE_EXIT!"=="0" (echo [ERROR] Preserve-data replacement failed with exit code !UPDATE_EXIT!.) else (echo Preserve-data database update completed. Restart local services.)
pause
exit /b !UPDATE_EXIT!
