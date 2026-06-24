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
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

echo Installing build dependencies...
"%PYTHON%" -m pip install -r "%~dp0requirements.txt" pyinstaller
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo Building exe, please wait 1-3 minutes...
"%PYTHON%" -m PyInstaller --noconfirm --clean "%~dp0better_coolpc.spec"
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Done: dist\BetterCoolPC\BetterCoolPC.exe
echo Copy the whole dist\BetterCoolPC folder to use it.
echo ========================================
pause
endlocal
