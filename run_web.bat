@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

rem Opens the KakaoBot web panel at http://127.0.0.1:8765/
rem Extra options are passed through, e.g.  run_web.bat --autostart
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py --web %*
    exit /b %errorlevel%
)

py -3.11 app.py --web %*
if errorlevel 1 (
    echo.
    echo [ERROR] Python 3.11 or the project dependencies are not available.
    echo         Install requirements.txt first.
    pause
)
