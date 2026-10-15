@echo off
setlocal EnableExtensions
chcp 65001 >nul
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONUTF8=1"
set "INIT_EXIT=1"
if not exist ".venv\Scripts\python.exe" goto :MISSING_PYTHON
if "%~1"=="" echo [Info] Checking NAS connection, schema compatibility, permissions and empty database...
".venv\Scripts\python.exe" -m scripts.initialize_nas_schema %*
set "INIT_EXIT=%ERRORLEVEL%"
if not "%~1"=="" goto :FINISH
if not "%INIT_EXIT%"=="0" goto :FINISH

echo.
echo The NAS database passed all preflight checks.
echo Initialize the complete schema and required system data now?
choice /C YN /N /M "Press Y to initialize, or N to cancel: "
if errorlevel 2 goto :CANCELLED
if errorlevel 1 goto :APPLY
set "INIT_EXIT=1"
goto :FINISH

:APPLY
echo.
echo [Info] Initializing NAS schema. All preflight checks will be repeated before writing...
".venv\Scripts\python.exe" -m scripts.initialize_nas_schema --apply
set "INIT_EXIT=%ERRORLEVEL%"
if "%INIT_EXIT%"=="0" echo [Done] NAS schema initialization completed.
goto :FINISH

:CANCELLED
echo.
echo [Cancelled] No schema initialization was requested.
goto :FINISH

:MISSING_PYTHON
echo [ERROR] Missing project Python .venv\Scripts\python.exe

:FINISH
echo.
if not "%INIT_EXIT%"=="0" echo [ERROR] NAS schema check or initialization stopped. Exit code: %INIT_EXIT%
if "%~1"=="" pause
exit /b %INIT_EXIT%
