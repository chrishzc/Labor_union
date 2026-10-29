@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0..\.."
set "MANAGER_ACTION=start"
set "MANAGER_LOCAL=-LocalOnly"
if /I "%~1"=="--connect" set "MANAGER_LOCAL="
if /I "%~1"=="--prepare" set "MANAGER_ACTION=prepare"
if /I "%~1"=="--dry-run" set "MANAGER_ACTION=check"
if /I "%~1"=="--update-frontend" set "MANAGER_ACTION=frontend"
if not "%~1"=="" if /I not "%~1"=="--prepare" if /I not "%~1"=="--dry-run" if /I not "%~1"=="--connect" if /I not "%~1"=="--update-frontend" exit /b 2
if not "%~2"=="" exit /b 2
@REM Compatibility entry for existing callers; lifecycle lives in one manager.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage_windows.ps1" -Action %MANAGER_ACTION% %MANAGER_LOCAL%
exit /b %ERRORLEVEL%
