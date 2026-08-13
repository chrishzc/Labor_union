@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

if /I "%~1"=="--dry-run" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_local_admin_no_auth.ps1" -DryRun
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  exit /b !DRY_RUN_EXIT!
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_local_admin_no_auth.ps1"
if %ERRORLEVEL% neq 0 (
  echo [Error] 腳本執行失敗，請先確認專案環境可用後重試。
  pause
  exit /b %ERRORLEVEL%
)

echo [Done] 已完成 `.env` 本機開發環境參數補齊：
echo  - APP_ENV=development
echo  - ENABLE_ADMIN_AUTH=false
pause
