@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "RESET_ROOT=%PROJECT_ROOT%\scratch\local_database_updates\operator_reset"
set "RESET_PLAN=%RESET_ROOT%\union_db.plan.json"
set "RESET_RECEIPT=%RESET_ROOT%\union_db.terminal.json"
if not exist "%PYTHON%" (
  echo [ERROR] Missing project Python: "%PYTHON%"
  pause
  exit /b 2
)
"%PYTHON%" -m scripts.launcher_preflight --profile database-reset
set "PREFLIGHT_EXIT=!ERRORLEVEL!"
if not "!PREFLIGHT_EXIT!"=="0" exit /b !PREFLIGHT_EXIT!
if /I "%~1"=="--dry-run" (
  "%PYTHON%" -m scripts.reset_fake_database --operator-reset --target-database union_db --dry-run --plan-receipt "%RESET_PLAN%"
  exit /b !ERRORLEVEL!
)
if not "%~1"=="" (
  "%PYTHON%" -m scripts.reset_fake_database %*
  exit /b !ERRORLEVEL!
)
echo Previewing destructive reset of local union_db from the current canonical schema...
"%PYTHON%" -m scripts.reset_fake_database --operator-reset --target-database union_db --plan-receipt "%RESET_PLAN%"
if errorlevel 1 (
  echo [ERROR] Reset preflight failed. Confirm .env targets local union_db and the canonical schema catalog is valid.
  pause
  exit /b 1
)
echo.
echo Stop API, UI, monitor, and workers before continuing.
echo This resets business data and preserves the existing root account and MFA binding.
echo Root password, encrypted MFA seed and recovery-code state are retained; no fixed key is generated.
echo An encrypted root backup is saved before DROP. Keep the existing TOTP encryption keyring.
echo Login sessions and non-root accounts are cleared. An unbound root still requires initial enrollment.
echo Canonical system seeds declared by schema artifacts may still be installed; no business fixture is loaded.
set /p "RESET_CONFIRM=Type RESET to continue: "
if /I not "!RESET_CONFIRM!"=="RESET" (
  echo Cancelled. No database changes were requested.
  exit /b 0
)
"%PYTHON%" -m scripts.reset_fake_database --operator-reset --target-database union_db --apply --confirm-apply RESET --plan-receipt "%RESET_PLAN%" --receipt-path "%RESET_RECEIPT%"
set "RESET_EXIT=!ERRORLEVEL!"
if not "!RESET_EXIT!"=="0" (echo [ERROR] Database reset failed with exit code !RESET_EXIT!. Review the retained root backup path.) else (echo Database reset completed with existing root authentication preserved. Restart local services.)
pause
exit /b !RESET_EXIT!
