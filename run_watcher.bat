@echo off
cd /d "%~dp0"
title Receipt Scanner - Watching app\incoming

:loop
python run.py
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% NEQ 0 (
    echo.
    echo Watcher exited unexpectedly with code %EXITCODE%. Restarting in 5 seconds...
    timeout /t 5 /nobreak >nul
    goto loop
)

echo Watcher stopped normally.
pause
