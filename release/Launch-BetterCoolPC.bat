@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "MISSING=0"

if not exist "%~dp0BetterCoolPC.exe" (
    echo [ERROR] Missing BetterCoolPC.exe
    set "MISSING=1"
)

if not exist "%~dp0_internal\" (
    echo [ERROR] Missing _internal folder
    set "MISSING=1"
)

if not exist "%~dp0_internal\templates\index.html" (
    echo [ERROR] Missing templates\index.html
    set "MISSING=1"
)

if "%MISSING%"=="1" (
    echo.
    echo Please unzip the full release package. Do not move only the exe file.
    pause
    exit /b 1
)

set "BROWSER_FOUND=0"
if exist "%LOCALAPPDATA%\Chromium\Application\chrome.exe" set "BROWSER_FOUND=1"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "BROWSER_FOUND=1"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER_FOUND=1"
if exist "%ProgramFiles%\Chromium\Application\chrome.exe" set "BROWSER_FOUND=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER_FOUND=1"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_FOUND=1"

if "%BROWSER_FOUND%"=="0" (
    echo [WARN] Chromium / Chrome / Edge not found.
    echo Install Chromium or Chrome, or set COOLPC_CHROMIUM_PATH to chrome.exe
    echo.
)

set COOLPC_DEBUG=0
set COOLPC_OPEN_BROWSER=1

echo Starting Better CoolPC...
echo Browser will open http://127.0.0.1:5000
echo Close this window to stop the server.
echo.

start "" /wait "%~dp0BetterCoolPC.exe"
if errorlevel 1 pause
endlocal
