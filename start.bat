@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Please install the dependencies first. See README.md.
    pause
    exit /b 1
)
start "" /b "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
