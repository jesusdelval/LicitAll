@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw scripts\launcher.py
) else (
    python scripts\launcher.py
    if errorlevel 1 pause
)
