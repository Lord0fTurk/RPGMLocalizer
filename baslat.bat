@echo off
cd /d "%~dp0"
echo RPGMLocalizer baslatiliyor...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    py -3.12 main.py
)
pause
