@echo off
goto :MAIN
@REM File: start_local_development_no_auth.bat
@REM Description: 以本機免登入 profile 啟動後端與 React 開發服務。
:MAIN
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "APP_ENV=development"
set "ENABLE_ADMIN_AUTH=false"
set "ACCESS_CONTROL_PROFILE=local_bypass"
set "VITE_ACCESS_CONTROL_PROFILE=local_bypass"
set "REACT_ADMIN_RUNTIME_PROFILE=source"
set "REACT_ADMIN_CURRENT_ARTIFACT_DIR="
set "REACT_ADMIN_PREVIOUS_ARTIFACT_DIR="
set "REACT_ADMIN_ACTIVE_SELECTOR="
if not defined ADMIN_ENTRY_TARGET_STATE_PATH set "ADMIN_ENTRY_TARGET_STATE_PATH=%ProgramData%\Labor_union\runtime\admin-entry-targets.json"

if /I "%~1"=="--dry-run" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_local_admin_no_auth.ps1" -DryRun
  if errorlevel 1 goto _bootstrap_failed
  call "%~dp0start_local_development.bat" --dry-run
  set "DRY_RUN_EXIT=!ERRORLEVEL!"
  exit /b !DRY_RUN_EXIT!
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_local_admin_no_auth.ps1"
if errorlevel 1 goto _bootstrap_failed

if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" goto _bootstrap_failed
set "LOCAL_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
for %%I in ("%ADMIN_ENTRY_TARGET_STATE_PATH%") do set "ENTRY_TARGET_STATE_PARENT=%%~dpI"
if not exist "%ENTRY_TARGET_STATE_PARENT%" mkdir "%ENTRY_TARGET_STATE_PARENT%"
if errorlevel 1 goto _bootstrap_failed
if exist "%ADMIN_ENTRY_TARGET_STATE_PATH%" (
  "%LOCAL_PYTHON%" -m scripts.provision_admin_entry_target_state attest --state "%ADMIN_ENTRY_TARGET_STATE_PATH%"
) else (
  "%LOCAL_PYTHON%" -m scripts.provision_admin_entry_target_state provision --template "%PROJECT_ROOT%\config\admin_entry_targets.initial.json" --output "%ADMIN_ENTRY_TARGET_STATE_PATH%"
)
if errorlevel 1 goto _bootstrap_failed
if not defined ANOMALY_ISSUE_IDENTITY_KEY_V1 (
  for /f "usebackq delims=" %%K in (`"%LOCAL_PYTHON%" -c "import secrets; print(secrets.token_urlsafe(32))"`) do set "ANOMALY_ISSUE_IDENTITY_KEY_V1=%%K"
)

call "%~dp0start_local_development.bat"
goto :eof

:_bootstrap_failed
echo [Error] bootstrap failed.
pause
exit /b 1
