@echo off
REM ===============================
REM AutoCAD PDF Reader Launcher
REM ===============================

REM -- Change drive/folder automatically if needed
cd /d %~dp0

REM -- Check Python installation
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3.12+ from https://www.python.org/
    pause
    exit /b
)

REM -- Set API keys (temporary for this session)
SET OPENAI_API_KEY=sk-your-openai-key
SET GROK_API_KEY=sk-your-grok-key

REM -- Install required packages
echo Installing dependencies (if not already installed)...
pip install -r requirements.txt

REM -- Run the program
echo Launching AutoCAD PDF Reader...
python drawingSystem.py

pause
