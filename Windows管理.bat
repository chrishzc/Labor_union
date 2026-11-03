@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

if not exist "%~dp0scripts\launchers\manage_windows.ps1" (
    echo [Error] Management script not found: "%~dp0scripts\launchers\manage_windows.ps1"
    echo Please make sure the project directory is complete.
    echo.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launchers\manage_windows.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% neq 0 (
    echo.
    echo [Notice] Execution exited abnormally with exit code: %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
