@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing project Python .venv\Scripts\python.exe
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.initialize_nas_schema %*
exit /b %ERRORLEVEL%
