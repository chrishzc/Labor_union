@echo off
setlocal EnableExtensions
@REM NAS MySQL connection comes from the existing .env DB_* settings.
set "APP_ENV=development"
set "RUNTIME_DATABASE_TARGET=nas"
call "%~dp0start_local_development.bat" %*
exit /b %ERRORLEVEL%
