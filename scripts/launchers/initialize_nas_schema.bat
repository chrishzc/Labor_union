@echo off
setlocal EnableExtensions
chcp 65001 >nul
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONUTF8=1"
set "INIT_EXIT=1"
if not exist ".venv\Scripts\python.exe" goto :MISSING_PYTHON
if "%~1"=="" goto :INTERACTIVE
".venv\Scripts\python.exe" -m scripts.initialize_nas_schema %*
set "INIT_EXIT=%ERRORLEVEL%"
goto :FINISH

:INTERACTIVE
echo.
echo [Info] Checking NAS connection, schema compatibility, permissions and database...
".venv\Scripts\python.exe" -m scripts.initialize_nas_schema --interactive
set "INIT_EXIT=%ERRORLEVEL%"
goto :FINISH

:MISSING_PYTHON
echo [ERROR] Missing project Python .venv\Scripts\python.exe

:FINISH
echo.
if not "%INIT_EXIT%"=="0" echo [ERROR] NAS schema check or initialization stopped. Exit code: %INIT_EXIT%
if "%~1"=="" pause
exit /b %INIT_EXIT%
