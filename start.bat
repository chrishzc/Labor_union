@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ==========================================
echo Labor Union Safe Startup Redirect
echo ==========================================
echo [Notice] start.bat no longer initializes the database or generates data.
echo [Notice] Starting the non-destructive online service launcher.

call "%~dp0online.bat"
exit /b %ERRORLEVEL%
