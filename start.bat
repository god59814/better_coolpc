@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON="
where python >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
    where py >nul 2>&1
    if not errorlevel 1 set "PYTHON=py -3"
)

if not defined PYTHON (
    echo [ERROR] Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

"%PYTHON%" -c "import flask, requests, bs4, lxml" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    "%PYTHON%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo [ERROR] pip install failed.
        pause
        exit /b 1
    )
)

set COOLPC_DEBUG=0
set COOLPC_OPEN_BROWSER=1
echo.
echo Starting Better CoolPC at http://127.0.0.1:5000
echo Close this window to stop the server.
echo.
"%PYTHON%" "%~dp0app.py"
if errorlevel 1 pause
endlocal
