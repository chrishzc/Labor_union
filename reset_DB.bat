@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [ERROR] Missing project Python: "%PYTHON%"
  pause
  exit /b 2
)
if "%~1"=="" (
  echo Resetting local union_db from the fixed v3 fixture...
  "%PYTHON%" -m scripts.reset_fake_database --apply --confirm-database union_db
  set "RESET_EXIT=!ERRORLEVEL!"
  if not "!RESET_EXIT!"=="0" (echo [ERROR] Database reset failed with exit code !RESET_EXIT!.) else (echo Database reset completed successfully.)
  pause
  exit /b !RESET_EXIT!
)
"%PYTHON%" -m scripts.reset_fake_database %*
exit /b %ERRORLEVEL%
