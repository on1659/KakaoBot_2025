@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "BUILD_PY=.venv-build\Scripts\python.exe"

if /I "%~1"=="--console" (
    set "KAKAOBOT_CONSOLE=1"
) else (
    set "KAKAOBOT_CONSOLE=0"
)

if not exist "%BUILD_PY%" (
    echo [1/4] Creating the Python 3.11 build environment...
    py -3.11 -m venv .venv-build
    if errorlevel 1 goto :error
)

echo [2/4] Installing runtime and build dependencies...
"%BUILD_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%BUILD_PY%" -m pip install --disable-pip-version-check --progress-bar off --prefer-binary -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

echo [3/4] Building KakaoBot...
"%BUILD_PY%" -m PyInstaller --noconfirm --clean KakaoBot.spec
if errorlevel 1 goto :error

echo [4/4] Build complete.
echo Output: %CD%\dist\KakaoBot\KakaoBot.exe
exit /b 0

:error
echo.
echo [ERROR] The build failed. Review the messages above.
exit /b 1
