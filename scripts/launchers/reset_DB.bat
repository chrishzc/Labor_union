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
if "%~1"=="" (
  echo Usage: reset_DB.bat --target-database lu_test_name [--dry-run ^| --apply ...]
  exit /b 2
)
if /I "%~1"=="--dry-run" (
  "%PYTHON%" -m scripts.launcher_preflight --profile database-reset
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  if not "!DRY_RUN_EXIT!"=="0" exit /b !DRY_RUN_EXIT!
) else if /I "%~2"=="--dry-run" (
  "%PYTHON%" -m scripts.launcher_preflight --profile database-reset
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  if not "!DRY_RUN_EXIT!"=="0" exit /b !DRY_RUN_EXIT!
)
"%PYTHON%" -m scripts.reset_fake_database %*
set "RESET_EXIT=!ERRORLEVEL!"
exit /b !RESET_EXIT!
