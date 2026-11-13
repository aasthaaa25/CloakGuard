@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "DEMO_PYTHON=.venv\Scripts\python.exe"
) else (
    set "DEMO_PYTHON=python"
)
"%DEMO_PYTHON%" demo_live.py --output "demo_outputs\run-%RANDOM%-%RANDOM%"
set "DEMO_EXIT=%ERRORLEVEL%"
if not "%DEMO_EXIT%"=="0" echo Demo failed. Install dependencies with python -m pip install -r results\requirements.txt
pause
exit /b %DEMO_EXIT%
