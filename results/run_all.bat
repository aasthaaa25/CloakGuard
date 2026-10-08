@echo off
REM Windows one-click run script
REM Double-click this file or run it in PowerShell/CMD

echo.
echo ============================================================
echo   Active Defense System -- Full Run (Windows)
echo ============================================================
echo.

python run_all.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [FAIL] run_all.py failed. See error above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo All done! Open report\report.html in your browser.
pause
