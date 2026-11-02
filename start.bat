@echo off
REM Phone-as-Keyboard launcher (Windows). Double-click this file.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating project environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv. Make sure Python 3 is installed.
        pause
        exit /b 1
    )
)

echo Installing requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

echo Starting server...
".venv\Scripts\python.exe" server.py %*
pause
