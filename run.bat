@echo off
title Tally Price List Uploader
echo ============================================
echo   Tally Price List Uploader - Setup & Run
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install flask flask-cors pandas openpyxl requests --break-system-packages >nul 2>&1
if %errorlevel% neq 0 (
    pip install flask flask-cors pandas openpyxl requests >nul 2>&1
)
echo Dependencies installed.
echo.

REM Set Tally URL (default: localhost:9000)
set TALLY_URL=http://localhost:9000
if not "%1"=="" set TALLY_URL=%1

echo Tally URL: %TALLY_URL%
echo.
echo IMPORTANT: Make sure Tally Prime is running with HTTP server enabled.
echo   In Tally: F1 (Help) ^> Settings ^> Advanced Configuration ^> Enable HTTP Server
echo   Default port: 9000
echo.
echo Starting server at http://localhost:5050
echo Open your browser and go to http://localhost:5050
echo.

python app.py
pause
