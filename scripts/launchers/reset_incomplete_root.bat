@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment not found.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.reset_incomplete_root_setup --apply
set "RESET_RESULT=%ERRORLEVEL%"
pause
exit /b %RESET_RESULT%
