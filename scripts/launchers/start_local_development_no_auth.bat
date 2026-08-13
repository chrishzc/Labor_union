@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

if /I "%~1"=="--dry-run" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_local_admin_no_auth.ps1" -DryRun
  if errorlevel 1 goto _bootstrap_failed
  call "%~dp0start_local_development.bat" --dry-run
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  exit /b !DRY_RUN_EXIT!
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_local_admin_no_auth.ps1"
if errorlevel 1 goto _bootstrap_failed

call "%~dp0start_local_development.bat"
goto :eof

:_bootstrap_failed
echo [Error] bootstrap failed.
pause
exit /b 1
