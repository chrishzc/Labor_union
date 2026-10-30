@echo off
setlocal EnableExtensions
chcp 65001 >nul
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo 找不到系統執行環境，請通知維護人員。
  if "%~1"=="" pause
  exit /b 2
)
".venv\Scripts\python.exe" -m scripts.nas_database_maintenance backup %*
set "MAINTENANCE_EXIT=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %MAINTENANCE_EXIT%
