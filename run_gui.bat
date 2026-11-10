@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
    exit /b %errorlevel%
)

py -3.11 app.py
if errorlevel 1 (
    echo.
    echo [ERROR] Python 3.11 or the project dependencies are not available.
    echo         Install requirements.txt or run build_exe.bat.
    pause
)

