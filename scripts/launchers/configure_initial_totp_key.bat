@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment not found.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.configure_initial_totp_key --apply
set "TOTP_RESULT=%ERRORLEVEL%"
pause
exit /b %TOTP_RESULT%
