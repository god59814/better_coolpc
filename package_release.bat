@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VERSION=%~1"
if "%VERSION%"=="" (
    echo Usage: package_release.bat v1.0.0
    echo Example: package_release.bat v1.0.0
    exit /b 1
)

set "PYTHON="
where python >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
    where py >nul 2>&1
    if not errorlevel 1 set "PYTHON=py -3"
)

if not defined PYTHON (
    echo [ERROR] Python not found. Required for building release.
    exit /b 1
)

echo [1/4] Installing build dependencies...
"%PYTHON%" -m pip install -r "%~dp0requirements.txt" pyinstaller
if errorlevel 1 exit /b 1

echo.
echo [2/4] Building executable...
"%PYTHON%" -m PyInstaller --noconfirm --clean "%~dp0better_coolpc.spec"
if errorlevel 1 exit /b 1

if not exist "%~dp0dist\BetterCoolPC\BetterCoolPC.exe" (
    echo [ERROR] dist\BetterCoolPC\BetterCoolPC.exe not found.
    exit /b 1
)

echo.
echo [3/4] Adding launcher files...
copy /Y "%~dp0release\Launch-BetterCoolPC.bat" "%~dp0dist\BetterCoolPC\" >nul
copy /Y "%~dp0release\README-Windows.txt" "%~dp0dist\BetterCoolPC\README.txt" >nul

if not exist "%~dp0release" mkdir "%~dp0release"

set "ZIP_NAME=BetterCoolPC-Windows-x64-%VERSION%.zip"
set "ZIP_PATH=%~dp0release\%ZIP_NAME%"

if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"

echo.
echo [4/4] Creating zip...
powershell -NoProfile -Command "Compress-Archive -Path '%~dp0dist\BetterCoolPC\*' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 (
    echo [ERROR] Failed to create zip.
    exit /b 1
)

echo.
echo ========================================
echo Release package ready:
echo %ZIP_PATH%
echo.
echo Publish to GitHub:
echo   gh release create %VERSION% "%ZIP_PATH%" --title "Better CoolPC %VERSION%" --notes "Windows x64 portable build"
echo ========================================
endlocal
